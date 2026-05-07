# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging
from datetime import datetime as dt

from odoo import models, fields, _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)

PAYMENT_TYPE_MAPPING = {
    'payment': ('last_customer_payment_point', 'invoice'),
    'billpayment': ('last_vendor_payment_point', 'bill'),
}


class QboMapPayment(models.Model):
    _name = 'qbo.map.payment'
    _inherit = 'qbo.map.abstract'
    _description = 'QuickBooks mapping: Payment, BillPayment'

    _related_odoo_field = 'payment_id'
    _qbo_class_names = ('Payment', 'BillPayment')

    _map_routes = {
        'qbo_name.payment_ref_num': ('PaymentRefNum', ''),
        'qbo_name.doc_number': ('DocNumber', ''),
        'currency_ref': ('CurrencyRef.value', ''),
        'pay_method': ('PaymentMethodRef.value', ''),
        'txn_date': ('TxnDate', ''),
    }

    payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Odoo Payment',
    )

    txn_id = fields.Many2one(
        comodel_name='qbo.map.account.move',
        string='Parent Invoice',
        ondelete='restrict',
    )

    invoice_id = fields.Many2one(
        related='txn_id.invoice_id',
    )

    txn_type = fields.Selection(
        related='txn_id.qbo_lib_type',
        string='Invoice Type',
    )

    txn_amount = fields.Char(
        string='Amount',
    )

    txn_date = fields.Char(
        string='Date',
    )

    pay_method = fields.Char(
        string='Payment Method',
    )

    currency_ref = fields.Char(
        string='Currency',
    )

    sync_token = fields.Char(
        string='Sync Token',
        default='0',
        help='Sync token increments after payment update.',
    )

    def fetch_resource_data_from_qbo(self, qi_id: int, *args, **kw):
        raise NotImplementedError('This method is not implemented for this model.')

    def trigger_sync_payments_in(self, qi_id: int, payment_type: str):
        """
        Getting the latest payments from the QuickBooks Company.
        :payment_type: `payment` or `billpayment`.
        """
        qi = self.env['quickbooks.integration'].browse(qi_id)
        fetch_point = qi._get_import_payments_fetch_point(*PAYMENT_TYPE_MAPPING[payment_type])

        if not fetch_point:
            _logger.info('There are no exported invoices for payments synchronizations for "%s".' % qi.name)
            return self.env['qbo.map.account.move']

        qb = qi.get_quickbooks_api_client()
        condition = "MetaData.LastUpdatedTime >= '%s' ORDERBY MetaData.LastUpdatedTime ASC" % fetch_point

        record_list = self._fetch_qbo_by_query(payment_type, condition, client=qb)

        if not record_list:
            _logger.info('There are no new QuickBooks payments for the "%s".', qi.name)
            return self.env['qbo.map.account.move']

        # Parse Invoice IDs from QuickBooks payment-records.
        invoices = set()
        for qbo_lib_model in record_list:
            lines = [x.to_dict() for x in qbo_lib_model.Line]
            txn_type = 'Invoice' if (payment_type == 'payment') else 'Bill'

            for l in lines:
                ids = [d['TxnId'] for d in l['LinkedTxn'] if d['TxnType'] == txn_type]
                invoices.update(ids)

        # Trigget update invoices with linked transactions.
        # No need to know payment.ids because we can get it from the invoice.LinkedTxn field
        invoice_mappings = self.env['qbo.map.account.move'].search([
            ('quickbooks_integration_id', '=', qi.id),
            ('qbo_id', 'in', list(invoices)),
            ('qbo_lib_type', '=', txn_type.lower()),
        ])

        invoice_mappings.action_import_invoice_payments()

        qi._update_import_payments_fetch_point(PAYMENT_TYPE_MAPPING[payment_type][0], record_list)

        _logger.info('%s: Triggerred payments import for the invoices qbo_ids=%s.', qi.name, invoice_mappings.ids)
        return invoice_mappings

    def _try_to_map_payment(self):
        self.ensure_one()

        invoice = self.invoice_id

        # 1. Try to map it automatically by name. Such flow is possible when the payment was pushed to API
        # but Odoo mapping wasn't created in some reasons. For example, import-payments-cron was executed
        # in the same time as payment was pushed or export job failed or whatever.
        invoice_payments = invoice.reconciled_payment_ids.filtered(lambda x: not x.is_qbo_sync_done)
        for payment in invoice_payments:
            name = payment.with_context(default_txn_id=self.txn_id.id) \
                ._prepare_pay_ref_number()

            if self.qbo_name == name:
                self.bind_odoo(payment.id)
                self._update_sync_token()
                return True

        return False

    def register_payment_in_odoo(self, reconcile=False):
        self.ensure_one()

        invoice = self.invoice_id

        # 2. If not found, create a new payment with the help of account.payment.register wizard.
        currency = self.env['res.currency'].search([
            ('name', '=', self.currency_ref),
        ], limit=1)

        # TODO: Convert currency to invoice currency

        values = {
            'amount': abs(float(self.txn_amount)),
            'currency_id': currency.id,
            'journal_id': self.get_payment_journal_id(),
            'payment_date': dt.strptime(self.txn_date, '%Y-%m-%d').date(),
        }

        if reconcile:
            values.update(
                **self._parse_writeoff_account_vals()
            )

        wizard = self.env['account.payment.register']\
            .with_context(active_model=invoice._name, active_ids=invoice.ids) \
            .create(values)

        # The original method "_create_payments" clears the context to skip "default_" fields,
        # so we need to use a custom context flag.
        payment = wizard \
            .with_context(mark_as_excluded_from_qbo_sync=True) \
            ._create_payments()

        self.bind_odoo(payment.id)

        # Let's save a SyncToken value we registered Odoo payment.
        # It may be helpful to know whether or not we need to register the payment again.
        self._update_sync_token()

        return payment

    def get_payment_journal_id(self):
        self.ensure_one()

        if self.pay_method:
            journal = self.env['qbo.map.payment.method'].search([
                ('qbo_id', '=', self.pay_method),
                ('quickbooks_integration_id', '=', self.quickbooks_integration_id.id),
            ], limit=1).journal_id

            if not journal:
                raise ValidationError(_(
                    '%s: It is not possible to register payment in Odoo. Please, '
                    'define in the menu [QuickBooks Online --> Mapping --> Payment Methods] "Odoo Journal" '
                    'for the "%s" payment method.' % (self.quickbooks_integration_id.name, self.pay_method)
                ))
        else:
            journal = self.quickbooks_integration_id.qi_default_journal_id

            if not journal:
                raise ValidationError(_(
                    '%s: It is not possible to register payment in Odoo. Please, '
                    'specify in the "Default Fields" tab of the Quickbooks Connection'
                    '"Default Payment Journal" field.' % self.quickbooks_integration_id.name
                ))

        return journal.id

    def _update_sync_token(self):
        self.sync_token = self.extract_node('SyncToken', '0')

    def _adjust_mapping_values(self, qi_id: int, values: dict, qbo_lib_model) -> dict:
        res = super(QboMapPayment, self)._adjust_mapping_values(qi_id, values, qbo_lib_model)

        name_dict = res.pop('qbo_name')
        if qbo_lib_model.is_payment:
            name = name_dict['payment_ref_num']
        else:
            name = name_dict['doc_number']

        res['qbo_name'] = name or f'Transaction/{qbo_lib_model.Id}'

        return res

    def _parse_writeoff_account_vals(self):
        account = self.quickbooks_integration_id.qi_default_write_off_account_id

        if not account:
            raise ValidationError(_(
                'It\'s not possible to register payment in Odoo. '
                'Specify `Default Write-off Account` in the module settings.'
            ))

        return {
            'writeoff_account_id': account.id,
            'payment_difference_handling': 'reconcile',
        }

    def _job_kwargs_register_payment(self):
        return {
            'identity_key': f'qbo-register-payment-{self.quickbooks_integration_id.id}-{self.id}',
            'description': f'Register payment "{self.qbo_name}" [qbo_id={self.qbo_id}]',
            'channel': self.job_channel,
        }
