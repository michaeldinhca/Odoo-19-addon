# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, fields, _
from odoo.exceptions import ValidationError

from ..quickbooks_api import QboDuplicateDocumentNumberError


class AccountPayment(models.Model):
    _name = 'account.payment'
    _inherit = [
        'account.payment',
        'quickbooks.mapping.mixin',
        'quickbooks.export.mixin',
    ]

    qbo_mapping_ids = fields.One2many(
        comodel_name='qbo.map.payment',
        inverse_name='payment_id',
        readonly=True,
    )

    @property
    def map_type(self):
        self.ensure_one()
        return self._partner_to_pay_type()

    @property
    def is_customer_invoice_payment(self):
        self.ensure_one()
        return self.partner_type == 'customer' and self.payment_type == 'inbound'

    @property
    def is_vendor_bill_payment(self):
        self.ensure_one()
        return self.partner_type == 'supplier' and self.payment_type == 'outbound'

    @property
    def payment_qbo_invoice_type(self):
        self.ensure_one()

        if self.is_customer_invoice_payment:
            return 'invoice'

        if self.is_vendor_bill_payment:
            return 'bill'

        raise ValidationError(_('Invalid payment type: %s' % self.payment_type))

    @property
    def qbo_reconcilled_field(self):
        self.ensure_one()
        return 'reconciled_invoice_ids' if self.partner_type == 'customer' else 'reconciled_bill_ids'

    @property
    def qbo_reconciled_ids(self):
        return self[self.qbo_reconcilled_field]

    def _partner_to_pay_type(self, partner_type=None):
        if not partner_type:
            self.ensure_one()
            partner_type = self.partner_type

        return 'payment' if partner_type == 'customer' else 'billpayment'

    def _pay_type_to_partner(self, pay_type):
        return 'customer' if pay_type == 'payment' else 'supplier'

    @property
    def is_qbo_export_allowed(self):
        self.ensure_one()

        qi = self.quickbooks_integration
        domain = qi.get_qbo_payment_domain()

        if not self.filtered_domain(domain):
            return False

        value = qi.qb_access_granted \
            and (self.state in ('in_process', 'paid')) \
            and not self.is_excluded_from_qbo_sync \
            and bool(self.qbo_reconciled_ids)

        if value and not self.env.context.get('qbo_invoice_export_allowed'):
            # We need to check if all related invoices are allowed to export to QBO if the context variable wasn't set
            return all(self.qbo_reconciled_ids.mapped(lambda x: x.is_qbo_sync_done or x.is_qbo_export_allowed))

        return value

    def action_export_to_quickbooks(self):
        count = 0

        for record in self:
            if not record.is_qbo_export_allowed:
                continue

            mapping = record._get_qbo_mapping()

            if mapping:
                record.mark_excluded_from_qbo_sync()
            else:
                count += 1
                job_kwargs = record._job_kwargs_qbo_transaction()
                record._mark_qbo_failed_jobs_as_cancel(identity_key=job_kwargs['identity_key'])

                record \
                    .with_context(company_id=record.company_id.id) \
                    .with_delay(**job_kwargs).export_qbo_one()

        return self._raise_jobs_notification(count)

    def export_qbo_one(self):
        self.ensure_one()

        if self.is_excluded_from_qbo_sync:
            return self._get_qbo_mapping()

        self = self.with_company(self.company_id)

        self._check_qbo_requirements()

        invoices = self.qbo_reconciled_ids

        if not all(x.is_qbo_sync_done for x in invoices):
            invoices.with_context(
                queue_job__no_delay=True,
                from_qbo_export_payment=True,
            ).action_export_to_quickbooks()

        if len(invoices) > 1:
            return self._export_qbo_one_to_many()

        return self._export_qbo_one_and_force_save(invoices.id, self.amount)

    def _export_qbo_one_to_many(self):
        self.ensure_one()

        chunks = self.qbo_reconciled_ids._get_amount_chunks_for_qbo_payments(self.amount)

        for (invoice_id, amount) in chunks:
            self._export_qbo_one_and_force_save(invoice_id, amount)

        return True

    def _export_qbo_one_and_force_save(self, invoice_id: int, amount: float):
        self.ensure_one()

        invoice = self.env['account.move'].browse(invoice_id)
        invoice_mapping = invoice._get_qbo_mapping()
        invoice_mapping.ensure_one()

        self_ = self.with_context(
            default_txn_amount=amount,
            default_txn_id=invoice_mapping.id,
        )

        qi = self.quickbooks_integration
        qbo_lib_model = self_._prepare_qbo_api_lib_instance(qi.id, invoice_id, amount=amount)

        try:
            mapping = self_._export_qbo_one(qi.id, qbo_lib_model)
        except QboDuplicateDocumentNumberError:
            mapping = self_._export_qbo_one_after_duplicate_check(qi.id, qbo_lib_model)

        # Mark payment as excluded from QuickBooks sync
        self_.mark_excluded_from_qbo_sync()

        return mapping

    def _prepare_qbo_api_lib_instance(self, qi_id: int, invoice_id: int, amount: float = None):
        qi = self.env['quickbooks.integration'].browse(qi_id)
        invoice = self.env['account.move'].browse(invoice_id)

        qbo_lib_model = self._init_qbo_lib_instance(self.map_type)

        if qi.derive_partner_from_invoice_to_payment:
            partner = invoice.partner_id
        else:
            partner = self.partner_id

        partner_mapping = partner._get_qbo_mapping(qi.id, invoice.qbo_partner_type)

        if invoice.is_customer_move_type:
            qbo_lib_model.CustomerRef = {
                'value': partner_mapping.qbo_id,
            }
            qbo_lib_model.PaymentRefNum = self._prepare_pay_ref_number()

            pay_method_rel = self.journal_id.get_qbo_related_payment_method(qi.id)
            qbo_lib_model.PaymentMethodRef = {
                'value': pay_method_rel.qbo_id,
            }
        else:
            qbo_lib_model.VendorRef = {
                'value': partner_mapping.qbo_id,
            }
            qbo_lib_model.PayType = 'Check'  # We are not supporting `CreditCard` for now
            qbo_lib_model.DocNumber = self._prepare_pay_ref_number()

            pay_account = self.journal_id.default_account_id
            account_rel = pay_account.get_qbo_related_account(qi.id)

            qbo_lib_model.CheckPayment = {
                'BankAccountRef': {
                    'name': account_rel.qbo_name,
                    'value': account_rel.qbo_id,
                }
            }

        currency = self.currency_id
        if currency != qi.currency_id:
            qbo_lib_model.ExchangeRate = currency.inverse_rate

        amount_ = amount or self.amount

        qbo_lib_model.TotalAmt = amount_
        qbo_lib_model.CurrencyRef = {'value': currency.name}
        qbo_lib_model.TxnDate = self.date.strftime('%Y-%m-%d')

        invoice = self.env['account.move'].browse(invoice_id)
        qbo_lib_model.Line = invoice._create_qbo_payment_line(amount_)

        return qbo_lib_model

    def _check_qbo_requirements(self, *args, **kw):
        self.ensure_one()

        if not self.qbo_reconciled_ids:
            raise ValidationError(_(
                'There is no any related invoice for the payment "%s".' % self.name
            ))

        journal = self.journal_id
        if not journal:
            raise ValidationError(_(
                'Journal is not defined for the payment "%s".' % self.display_name
            ))

        qi = self.company_id.quickbooks_integration

        if self.partner_type == 'customer':
            journal.get_qbo_related_payment_method(qi.id)
        else:
            account = journal.default_account_id

            if not account:
                raise ValidationError(_(
                    'Account for the journal "%s" is not defined.' % (journal.name)
                ))

            account.get_qbo_related_account(qi.id)

    def _prepare_pay_ref_number(self):
        name = self.name
        txn_id = self.env.context.get('default_txn_id')
        if txn_id:
            record = self.env['qbo.map.account.move'].browse(txn_id)
            name = f'{name}-{record.qbo_id}'
        return name[:21]

    def _get_condition_for_check_qbo_duplicate(self, qbo_lib_model):
        if qbo_lib_model.is_billpayment:
            return f"DocNumber = '{qbo_lib_model.DocNumber}'"
        return f"PaymentRefNum = '{qbo_lib_model.PaymentRefNum}'"

    def _get_qbo_mapping(self, *args, **kw):
        self.ensure_one()
        qi = self.quickbooks_integration

        return self.qbo_mapping_ids \
            .filtered(
                lambda r: r.qbo_lib_type == self.map_type and r.quickbooks_integration_id == qi
            )

    def to_qbo_json(self):
        self._check_qbo_requirements()

        invoices = self.qbo_reconciled_ids

        if not all(x.is_qbo_sync_done for x in invoices):
            names = invoices.filtered(lambda x: not x.is_qbo_sync_done).mapped('display_name')
            raise ValidationError(_('Please export the related invoice first: %s!' % ', '.join(names)))

        qi = self.quickbooks_integration

        if len(invoices) > 1:
            payload = {}
            for (invoice_id, amount) in invoices._get_amount_chunks_for_qbo_payments(self.amount):
                qbo_lib_model = self._prepare_qbo_api_lib_instance(qi.id, invoice_id, amount)
                payload[invoice_id] = qbo_lib_model.to_dict()
        else:
            qbo_lib_model = self._prepare_qbo_api_lib_instance(qi.id, invoices.id, self.amount)
            payload = qbo_lib_model.to_dict()

        return self.env['quickbooks.help.wizard'].create_and_run_as_json(
            f'DEBUG: {self.name} [{self.map_type}]',
            payload,
        )
