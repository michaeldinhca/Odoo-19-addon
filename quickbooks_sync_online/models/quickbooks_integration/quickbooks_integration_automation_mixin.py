# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import api, models, fields

from ...tools import parse_datetime_from_str, convert_datetime_to_str


_logger = logging.getLogger(__name__)


class QuickbooksIntegrationAutomationMixin(models.AbstractModel):
    _name = 'quickbooks.integration.automation.mixin'
    _description = 'Quickbooks Integration Automation Mixin'

    # Automatic actions
    enable_invoices_auto_export = fields.Boolean(
        string='Auto-export Invoices to QuickBooks',
    )

    enable_payments_sync_in = fields.Boolean(
        string='Auto-import Payments from QuickBooks',
        help='Allow to import payments related to already synchronized customer invoices and vendor bills',
    )

    enable_payments_sync_out = fields.Boolean(
        string='Auto-export Payments to QuickBooks',
        help=(
            'Allow to export payments related to already synchronized customer invoices and vendor bills'
        ),
    )

    payments_import_next_call_point = fields.Datetime(
        string='Upcoming Payments Import',
        compute='_compute_automation_points',
    )

    payments_export_next_call_point = fields.Datetime(
        string='Upcoming Payments Export',
        compute='_compute_automation_points',
    )

    last_customer_payment_point = fields.Char(
        string='Last Customer Payment Point',
        help=(
            'The last synchronized customer-type payments datetime point.'
        ),
    )

    last_vendor_payment_point = fields.Char(
        string='Last Vendor Payment Point',
        help=(
            'The last synchronized vendor-type payments datetime point.'
        ),
    )

    auto_export_cut_off_date = fields.Date(
        string='Invoices Cut-off Date',
        required=True,
        default=fields.Date.today(),
    )

    auto_export_batch_limit = fields.Integer(
        string='Batch Export Limit',
        default=10,
        required=True,
    )

    auto_export_next_call_point = fields.Datetime(
        string='Upcoming Invoices Export',
        compute='_compute_automation_points',
    )

    # Invoices
    allow_out_invoice_export = fields.Boolean(
        string='Customer Invoice',
    )

    allow_out_refund_export = fields.Boolean(
        string='Customer CreditNote',
    )

    allow_in_invoice_export = fields.Boolean(
        string='Vendor Bill',
    )

    allow_in_refund_export = fields.Boolean(
        string='Vendor Refund',
    )

    export_invoice_as_tax_included = fields.Boolean(
        string='Send as Tax Included',
    )

    derive_partner_from_invoice_to_payment = fields.Boolean(
        string='Derive Partner from Invoice to Payment',
    )

    # Products options
    include_product_to_invoice = fields.Boolean(
        string='Include Products in Invoices',
        default=True,
        help=(
            'Include products in customer invoices/refunds during export to QuickBooks.'
        ),
    )

    sync_product_as_category = fields.Boolean(
        string='Sync Products as Categories',
        help=(
            'Send products as category during invoice export to QuickBooks (all invoice types)'
        ),
    )

    send_storable_product_as_consumable = fields.Boolean(
        string='Export Storable Products as Consumables',
        help=('Send storable products as consumable during product export to QuickBooks.'),
    )

    sync_product_stock = fields.Boolean(
        string='Include Stock Quantities in Export',
        help=(
            'Send product stock to QuickBooks. '
            'During the first time export of storables products a stock quantity will be sent anyway '
            '(QuickBooks requirement). In further exports, stock will be sent only if this option is enabled.'
        ),
    )

    # Updates
    enable_updates_auto_export = fields.Boolean(
        string='Automatic Updates to QuickBooks',
        help=(
            'Allow sending automatic updates for partners, products, to QuickBooks.'
        ),
    )

    allow_update_partners = fields.Boolean(
        string='Allow Partners Updates',
        help=(
            'Allow updating partners in QuickBooks.'
        ),
    )

    allow_update_products = fields.Boolean(
        string='Allow Products Updates',
        help=(
            'Allow updating products in QuickBooks.'
        ),
    )

    send_update_next_call_point = fields.Datetime(
        string='Upcoming Update',
        compute='_compute_automation_points',
    )

    def _compute_automation_points(self):
        for rec in self:
            rec.auto_export_next_call_point = rec._compute_point('trigget_send_invoices_to_qb_cron')
            rec.payments_import_next_call_point = rec._compute_point('trigget_receive_qb_payments_cron')
            rec.payments_export_next_call_point = rec._compute_point('trigger_export_quickbooks_payments_cron')
            rec.send_update_next_call_point = rec._compute_point('trigger_send_updates_to_qb_cron')

    def _compute_point(self, cron_xml_id: str):
        cron = self.env.ref(f'quickbooks_sync_online.{cron_xml_id}', raise_if_not_found=False)
        return cron.nextcall if cron else False

    @api.model
    def import_quickbooks_payments_cron(self):
        """Get new payments from QuickBooks Company."""
        for qi in self.get_quickbooks_integrations([('enable_payments_sync_in', '=', True)]):
            qi.import_quickbooks_payments()

        return True

    def import_quickbooks_payments(self):
        self.ensure_one()
        MapPayment = self.env['qbo.map.payment'].with_company(self.company_id)

        if self.allow_out_invoice_export:
            MapPayment.trigger_sync_payments_in(self.id, 'payment')

        if self.allow_in_invoice_export:
            MapPayment.trigger_sync_payments_in(self.id, 'billpayment')

        return True

    @api.model
    def export_invoices_to_quickbooks_cron(self):
        for qi in self.get_quickbooks_integrations([('enable_invoices_auto_export', '=', True)]):
            qi.export_invoices_to_quickbooks()

        return True

    def export_invoices_to_quickbooks(self):
        self.ensure_one()
        invoices = self._search_to_qbo_invoices(limit=self.auto_export_batch_limit)
        return invoices.action_export_to_quickbooks()

    @api.model
    def export_payments_to_quickbooks_cron(self):
        """Export new payments to the Intuit Company."""
        for qi in self.get_quickbooks_integrations([('enable_payments_sync_out', '=', True)]):
            qi.export_payments_to_quickbooks()

        return True

    def export_payments_to_quickbooks(self):
        self.ensure_one()
        payments = self._search_to_qbo_payments(limit=self.auto_export_batch_limit)
        return payments.action_export_to_quickbooks()

    @api.model
    def update_records_to_quickbooks_cron(self):
        """Update records to the QuickBooks Company."""
        qis = self.get_quickbooks_integrations([('enable_updates_auto_export', '=', True)])
        if not qis:
            return False

        partners = self.env['res.partner']
        if any(qi.allow_update_partners for qi in qis):
            partners = self.env['res.partner'].search([('is_qbo_update_required', '=', True)])

        products = self.env['product.product']
        if any(qi.allow_update_products for qi in qis):
            products = self.env['product.product'].search([('is_qbo_update_required', '=', True)])

        for qi in qis:
            if qi.allow_update_partners:
                qi._action_update_records_to_quickbooks(partners)

            if qi.allow_update_products:
                qi._action_update_records_to_quickbooks(products)

        partners.unmark_for_qbo_update()
        products.unmark_for_qbo_update()

        return True

    def _action_update_records_to_quickbooks(self, records: models.Model):
        for map_type in records.map_types:
            records_to_update = records.browse()

            for record in records:
                mapping = record._get_qbo_mapping(self.company_id.id, map_type)
                if len(mapping) == 1:
                    records_to_update |= record

            if records_to_update:
                records_to_update.with_company(self.company_id).action_export_to_quickbooks()

        return True

    def _search_to_qbo_invoices(self, limit=None):
        self.ensure_one()
        company = self.company_id

        invoices = self.env['account.move'].with_company(company).search(
            [
                ('company_id', '=', company.id),
                ('state', '=', 'posted'),
                ('is_excluded_from_qbo_sync', '=', False),
                ('invoice_date', '>=', self.auto_export_cut_off_date),
                ('move_type', 'in', self.get_qbo_invoice_allowed_types()),
            ],
            limit=limit,
            order='invoice_date,id',
        )
        return invoices

    def _search_to_qbo_payments(self, limit=None):
        self.ensure_one()
        company = self.company_id

        payments = self.env['account.payment'].with_company(company).search(
            [
                ('company_id', '=', company.id),
                ('state', 'in', ['in_process', 'paid']),
                ('is_excluded_from_qbo_sync', '=', False),
                ('date', '>=', self.auto_export_cut_off_date),
            ],
            limit=limit,
            order='date,id',
        )

        domain = self.get_qbo_payment_domain()
        return payments.filtered_domain(domain)

    def get_qbo_invoice_allowed_types(self):
        self.ensure_one()
        types = []

        if self.allow_out_invoice_export:
            types.append('out_invoice')
        if self.allow_out_refund_export:
            types.append('out_refund')
        if self.allow_in_invoice_export:
            types.append('in_invoice')
        if self.allow_in_refund_export:
            types.append('in_refund')

        return types

    def get_qbo_payment_domain(self):
        self.ensure_one()
        domain_1 = domain_2 = []

        _manual_trigger = self.env.context.get('qbo_export_payment_manual')

        if self.allow_out_invoice_export or _manual_trigger:
            domain_1 = fields.Domain.AND([
                [('payment_type', '=', 'inbound')],
                [('partner_type', '=', 'customer')],
            ])

        if self.allow_in_invoice_export or _manual_trigger:
            domain_2 = fields.Domain.AND([
                [('payment_type', '=', 'outbound')],
                [('partner_type', '=', 'supplier')],
            ])

        if domain_1 and domain_2:
            return fields.Domain.OR([domain_1, domain_2])
        return domain_1 or domain_2

    def _get_import_payments_fetch_point(self, name_field: str, mapping_type: str):
        date_field_value = getattr(self, name_field)

        if parse_datetime_from_str(date_field_value):
            return date_field_value

        condition = """
            SELECT MIN(create_date) FROM qbo_map_account_move
            WHERE quickbooks_integration_id = %s AND qbo_lib_type = %s
        """

        self.env.cr.execute(condition, [self.id, mapping_type])
        result = self.env.cr.fetchone()

        point = result[0] and result[0].replace(minute=0, hour=0, second=0, microsecond=0)
        return convert_datetime_to_str(point)

    def _update_import_payments_fetch_point(self, name_field: str, record_list: list):
        result = []

        for qbo_lib_model in record_list:
            metadata = qbo_lib_model.MetaData

            if isinstance(metadata, dict):
                value = metadata.get('LastUpdatedTime')
            else:
                value = getattr(metadata, 'LastUpdatedTime', False)

            if value:
                result.append(value)

        if result:
            self[name_field] = result[-1]
