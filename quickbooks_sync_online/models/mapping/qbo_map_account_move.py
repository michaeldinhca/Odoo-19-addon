# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from typing import List, Dict

from odoo import fields, models


class QboMapAccountMove(models.Model):
    _name = 'qbo.map.account.move'
    _inherit = [
        'qbo.map.abstract',
        'qbo.map.tax.mixin',
    ]
    _description = 'QuickBooks mapping: Invoice, Credit Memo, Bill, Vendor Credit'

    _related_odoo_field = 'invoice_id'
    _qbo_class_names = ('Invoice', 'CreditMemo', 'Bill', 'VendorCredit')

    _map_routes = {
        'qbo_name': ('DocNumber', ''),
        'total_amt': ('TotalAmt', 0),
        'invoice_link': ('InvoiceLink', ''),
        'total_tax': ('TxnTaxDetail.TotalTax', 0),
    }

    total_amt = fields.Float(
        string='Amount Total',
        readonly=True,
    )

    total_tax = fields.Float(
        string='Tax Total',
        readonly=True,
    )

    qbo_tax_ids = fields.Many2many(
        comodel_name='qbo.map.tax',
        string='QuickBooks Taxes',
    )

    invoice_link = fields.Char(
        string='Invoice Link',
        readonly=True,
    )

    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Odoo Invoice',
        domain='[("company_id", "=", company_id)]',
    )

    partner_id = fields.Many2one(
        related='invoice_id.partner_id',
    )

    payment_state = fields.Selection(
        related='invoice_id.payment_state',
    )

    payment_ids = fields.One2many(
        comodel_name='qbo.map.payment',
        inverse_name='txn_id',
        string='Map Payments',
    )

    invoice_map_line_ids = fields.One2many(
        comodel_name='qbo.map.invoice.line',
        inverse_name='invoice_map_id',
        string='Map Invoice Lines',
    )

    @property
    def is_invoice(self):
        return self.map_type == 'invoice'

    @property
    def is_creditmemo(self):
        return self.map_type == 'creditmemo'

    @property
    def is_bill(self):
        return self.map_type == 'bill'

    @property
    def is_vendorcredit(self):
        return self.map_type == 'vendorcredit'

    @property
    def is_customer_type(self):
        return self.is_invoice or self.is_creditmemo

    @property
    def is_vendor_type(self):
        return self.is_bill or self.is_vendorcredit

    def fetch_resource_data_from_qbo(self, qi_id: int, *args, **kw):
        raise NotImplementedError('This method is not implemented for this model.')

    def action_import_invoice_payments_button(self):
        self.ensure_one()

        self.with_context(
            qbo_skip_payment_registration=False,
        ).action_import_invoice_payments()

        return self.invoice_id._raise_jobs_notification(len(self))

    def action_import_invoice_payments(self):
        for mapping in self:
            if mapping.is_vendorcredit or mapping.is_creditmemo:
                continue

            qi = mapping.quickbooks_integration_id
            job_kwargs = mapping._job_kwargs_import_payments()
            self.env['queue.job'].cancel_failed_jobs_by_identity_key(job_kwargs['identity_key'])

            company = qi.company_id
            mapping_ = mapping.with_company(company).with_context(company_id=company.id)
            skip_registration_ = bool(mapping.env.context.get('qbo_skip_payment_registration'))

            mapping_.with_delay(**job_kwargs) \
                .import_payments(skip_registration=skip_registration_)

    def import_payments(self, pay_ids: list = None, skip_registration: bool = False):
        """
        Sync external payments from QuickBooks to Odoo.

        This method is used to sync and register external payments from QuickBooks to Odoo.
        It will actualize the external payment mappings and then register the payments.

        :return: None
        """
        self.actualize_payment_mappings(pay_ids)

        payments = self.payment_ids.filtered(lambda x: not x.payment_id)

        if not skip_registration:
            zero_balance = (self.extract_node('Balance', 0) == 0)

            for idx, payment in enumerate(payments, start=1):
                if payment._try_to_map_payment():
                    continue

                job_kwargs = payment._job_kwargs_register_payment()
                self.env['queue.job'].cancel_failed_jobs_by_identity_key(job_kwargs['identity_key'])

                payment \
                    .with_context(company_id=payment.company_id.id) \
                    .with_delay(**job_kwargs) \
                    .register_payment_in_odoo(
                        reconcile=(idx == len(payments) and zero_balance),
                    )

    def actualize_payment_mappings(self, pay_ids: list = None):
        """
        Actualize the external payment mappings.

        This method is used to actualize the external payment mappings.
        It will fetch the external payments from QuickBooks and then create the payment mappings.

        :return: None
        """
        payments = self.get_payments_from_qbo(pay_ids)

        for payment in payments:
            mapping = self.payment_ids.filtered(lambda x: x.qbo_id == payment.Id)

            if mapping:
                mapping.update_qbo_mapping_from_response(payment)
            else:
                amount = self._parse_transaction_amount([l.to_dict() for l in payment.Line])

                mapping = self.env['qbo.map.payment'] \
                    .with_context(default_txn_id=self.id, default_txn_amount=amount) \
                    .create_qbo_mapping_from_response(payment, self.quickbooks_integration_id.id, odoo_id=None)

        return self.payment_ids

    def get_payments_from_qbo(self, pay_ids: list = None):
        self.ensure_one()

        payment_type = 'Payment' if self.is_customer_type else 'BillPaymentCheck'

        if not pay_ids:
            qbo_lib_object = self.fetch_qbo_one()
            self.update_qbo_mapping_from_response(qbo_lib_object)

            pay_ids = [x.TxnId for x in qbo_lib_object.LinkedTxn if x.TxnType == payment_type]

        if not pay_ids:
            return []

        ids = list(set(pay_ids))
        ids.sort(key=int)
        condition = "Id IN (%s)" % ", ".join(repr(i) for i in ids)

        qb = self.quickbooks_integration_id.get_quickbooks_api_client()
        payments = self._fetch_qbo_by_query(payment_type, condition, client=qb)

        return payments

    def apply_taxes_from_intuit(self):
        self._recompute_map_lines()

        for tax in self.qbo_tax_ids.filtered(lambda r: not r.tax_id):
            tax.sudo().try_to_map(summary=False)

        zipper = zip(
            self.invoice_id.invoice_line_ids.filtered(lambda x: x.display_type_product),
            self.invoice_map_line_ids,
        )

        lines = []
        for invoice_line, map_line in zipper:
            taxes = map_line.tax_map_ids.mapped('tax_id')

            lines.append(
                (1, invoice_line.id, {'tax_ids': [(6, 0, taxes.ids)]}),
            )

        return self.invoice_id \
            .write({'invoice_line_ids': lines})

    def _parse_transaction_amount(self, lines: List[Dict]):
        txn_id = self.qbo_id
        txn_type = self.qbo_entity_name

        for line in lines:
            if any(x['TxnId'] == txn_id and x['TxnType'] == txn_type for x in line['LinkedTxn']):
                return line['Amount']

        return 0

    def _prepare_map_lines(self, qbo_lib_model):
        res = super(QboMapAccountMove, self)._prepare_map_lines(qbo_lib_model)

        for data in res:
            data['invoice_map_id'] = self.id

        return res

    def _recompute_map_lines(self):
        # 0. Unlink old values for recomputing
        self.qbo_tax_ids = [(6, 0, [])]
        self.invoice_map_line_ids.unlink()

        qbo_lib_model = self.init_from_stored_json()
        # 1. Parse taxes
        map_tax = self._parse_map_tax_ids(self.quickbooks_integration_id.id, qbo_lib_model.TxnTaxDetail)
        self.qbo_tax_ids = [(6, 0, map_tax.ids)]
        # 2. Create map-lines
        vals_list = self._prepare_map_lines(qbo_lib_model)
        self.env['qbo.map.invoice.line'].create(vals_list)

    def _job_kwargs_import_payments(self):
        return {
            'identity_key': f'qbo-import-invoice-payments-{self.quickbooks_integration_id.id}-{self.qbo_id}',
            'description': f'Import payments for Invoice "{self.qbo_name}" [qbo_id={self.qbo_id}]',
            'channel': self.job_channel,
        }
