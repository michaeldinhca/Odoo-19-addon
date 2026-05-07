# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging
import json

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError

from ..quickbooks_api import QboDuplicateDocumentNumberError


_logger = logging.getLogger(__name__)

QBO_DIFF_TOTAL_WARNING = (
    'Difference in total invoice amounts in Quickbooks and Odoo. You cannot apply received taxes '
    'because your administrator turned off products synchronisation in Quickbooks Connection.'
)
QBO_APPLY_TAXES_WARNING = (
    'Difference in total invoice amounts in Quickbooks and Odoo. '
    'Invoice amount in Quickbooks is %s. Invoice amount in Odoo is %s. '
    'Usually that happens because of Quickbooks calculate taxes itself. '
    'Click "Apply QuickBooks Taxes" button to synchronise taxes between Quickbooks and Odoo. '
    'Note that "Apply QuickBooks Taxes" button is visible only in Draft status.'
)
TAX_INCLUDED = 'TaxInclusive'
TAX_EXCLUDED = 'TaxExcluded'


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = [
        'account.move',
        'quickbooks.mapping.mixin',
        'quickbooks.export.mixin',
    ]

    qbo_mapping_ids = fields.One2many(
        comodel_name='qbo.map.account.move',
        inverse_name='invoice_id',
        readonly=True,
    )
    qbo_warning_txt = fields.Char(
        string='QuickBooks Attention',
        compute='_compute_qbo_warning',
    )
    qbo_invoice_link = fields.Char(
        string='QuickBooks Invoice Link',
        compute='_compute_qbo_invoice_link',
    )

    @property
    def is_customer_invoice(self):
        self.ensure_one()
        return self.move_type == 'out_invoice'

    @property
    def is_customer_refund(self):
        self.ensure_one()
        return self.move_type == 'out_refund'

    @property
    def is_vendor_bill(self):
        self.ensure_one()
        return self.move_type == 'in_invoice'

    @property
    def is_vendor_refund(self):
        self.ensure_one()
        return self.move_type == 'in_refund'

    @property
    def is_customer_move_type(self):
        self.ensure_one()
        return self.move_type in ('out_invoice', 'out_refund')

    @property
    def is_vendor_move_type(self):
        self.ensure_one()
        return self.move_type in ('in_invoice', 'in_refund')

    @property
    def qbo_partner_type(self):
        self.ensure_one()
        return 'customer' if self.is_customer_move_type else 'vendor'

    @property
    def qbo_invoice_line_ids(self):
        self.ensure_one()
        return self.invoice_line_ids.filtered(lambda x: x.display_type_product)

    @property
    def invoice_payments_widget_content(self):
        self.ensure_one()
        invoice_payments_widget = self.invoice_payments_widget

        try:
            if not isinstance(invoice_payments_widget, dict):
                invoice_payments_widget = json.loads(invoice_payments_widget)
        except Exception:
            return []

        return invoice_payments_widget.get('content') or []

    @api.depends('qbo_mapping_ids', 'state', 'is_qbo_sync_done')
    def _compute_qbo_warning(self):
        move_types = ('out_invoice', 'out_refund')
        for rec in self:
            info = False

            if rec.move_type in move_types:
                if rec.is_customer_invoice:
                    mapping = rec.qbo_mapping_ids.filtered(lambda x: x.is_invoice)
                else:
                    mapping = rec.qbo_mapping_ids.filtered(lambda x: x.is_creditmemo)

                amount = rec.amount_total
                mapping_amount = mapping.total_amt

                if amount and mapping_amount and (abs(amount - mapping_amount) > 0.05):
                    if not rec.quickbooks_integration.include_product_to_invoice:
                        info = QBO_DIFF_TOTAL_WARNING
                    else:
                        info = QBO_APPLY_TAXES_WARNING % (mapping_amount, amount)

            rec.qbo_warning_txt = info

    @api.depends('qbo_mapping_ids', 'is_qbo_sync_done')
    def _compute_qbo_invoice_link(self):
        for rec in self:
            rec.qbo_invoice_link = rec.qbo_mapping_ids.filtered(lambda x: x.is_invoice).invoice_link

    def _get_condition_for_check_qbo_duplicate(self, qbo_lib_model):
        return f"DocNumber = '{qbo_lib_model.DocNumber}'"

    @property
    def map_type(self):
        self.ensure_one()

        if self.is_customer_invoice:
            return 'invoice'
        elif self.is_customer_refund:
            return 'creditmemo'
        elif self.is_vendor_bill:
            return 'bill'
        elif self.is_vendor_refund:
            return 'vendorcredit'

        return super().map_type

    @property
    def is_qbo_export_allowed(self):
        qi = self.quickbooks_integration

        return qi.qb_access_granted \
            and (self.state == 'posted') \
            and (self.move_type in qi.get_qbo_invoice_allowed_types()) \
            and not self.is_excluded_from_qbo_sync

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

        company = self.company_id
        self = self.with_company(company)

        # Check requirements
        self._check_qbo_requirements()

        # Export products if no mapping found
        qi = company.quickbooks_integration

        # Export main partner if no mapping found
        partner = self.partner_id._ensure_qbo_currency(self)
        partner_mapping = partner._get_qbo_mapping(qi.id, self.qbo_partner_type)

        if not partner_mapping:
            partner_mapping = partner.export_qbo_one(qi.id, self.qbo_partner_type)
        partner_mapping.ensure_one()

        # Export products if no mapping found
        products = self._get_products_to_qbo_export()
        for product in products:
            product_mapping = product._get_qbo_mapping(qi.id, 'item')

            if not product_mapping:
                product_mapping = product.export_qbo_one(qi.id)
            product_mapping.ensure_one()

        # Export source customer if no mapping found for vendor bill/refund
        if self.is_vendor_move_type:
            partners = self.qbo_invoice_line_ids \
                .mapped('purchase_line_id.sale_line_id.order_id.partner_id')

            for partner in partners._ensure_qbo_currency(self):
                partner_mapping = partner._get_qbo_mapping(qi.id, 'customer')

                if not partner_mapping:
                    partner_mapping = partner.export_qbo_one(qi.id, 'customer')
                partner_mapping.ensure_one()

        # Prepare invoice qbo-lib instance
        qbo_lib_model = self._prepare_qbo_api_lib_instance(qi.id)

        # Export invoice
        try:
            mapping = self._export_qbo_one(qi.id, qbo_lib_model)
        except QboDuplicateDocumentNumberError:
            mapping = self._export_qbo_one_after_duplicate_check(qi.id, qbo_lib_model)

        # Mark invoice as excluded from QuickBooks sync
        self.mark_excluded_from_qbo_sync()

        # Export payments if payment sync is enabled
        if qi.enable_payments_sync_out and not self.env.context.get('from_qbo_export_payment'):
            self.reconciled_payment_ids \
                .with_context(qbo_invoice_export_allowed=True) \
                .action_export_to_quickbooks()

        return mapping

    def _prepare_qbo_api_lib_instance(self, qi_id: int):
        qi = self.env['quickbooks.integration'].browse(qi_id)
        qbo_lib_model = self._init_qbo_lib_instance(self.map_type)

        partner = self.partner_id._ensure_qbo_currency(self)
        qbo_partner = partner._get_qbo_mapping(qi.id, self.qbo_partner_type)

        if qi.qb_is_us_company:
            tax_calculation = TAX_EXCLUDED
        else:
            tax_calculation = TAX_INCLUDED if qi.export_invoice_as_tax_included else TAX_EXCLUDED

        qbo_lib_model.GlobalTaxCalculation = tax_calculation

        if self.ref:
            qbo_lib_model.PrivateNote = self.ref

        if self.is_customer_move_type:
            qbo_lib_model.CustomerRef = {
                'value': qbo_partner.qbo_id,
            }
            qbo_lib_model.DepartmentRef = {
                'value': self._get_qbo_department(),
            }
            if self.is_customer_invoice:
                qbo_lib_model.BillEmail = {'Address': self.partner_id.email or ''}
                qbo_lib_model.AllowOnlineACHPayment = True
                qbo_lib_model.AllowOnlineCreditCardPayment = True

            if self.partner_shipping_id:
                qbo_lib_model.ShipAddr = self.partner_shipping_id._format_to_qbo_address()

        elif self.is_vendor_move_type:
            pay_account = self.partner_id.property_account_payable_id
            account_rel = pay_account.get_qbo_related_account(qi.id)

            qbo_lib_model.VendorRef = {
                'value': qbo_partner.qbo_id,
            }
            qbo_lib_model.APAccountRef = {
                'name': account_rel.qbo_name,
                'value': account_rel.qbo_id,
            }

        if self.currency_id != qi.currency_id:
            qbo_lib_model.ExchangeRate = self.currency_id.inverse_rate

        qbo_lib_model.DocNumber = self.name
        qbo_lib_model.CurrencyRef = {
            'value': self.currency_id.name,
        }
        if self.invoice_date:
            qbo_lib_model.TxnDate = self.invoice_date.strftime('%Y-%m-%d')

        if self.invoice_date_due and not self.invoice_payment_term_id:
            if self.is_customer_invoice or self.is_vendor_bill:
                qbo_lib_model.DueDate = self.invoice_date_due.strftime('%Y-%m-%d')
        elif self.invoice_payment_term_id:
            if self.is_customer_invoice or self.is_vendor_bill or self.is_customer_refund:
                qbo_rel_term = self.invoice_payment_term_id.get_qbo_related_payment_term(qi.id)
                qbo_lib_model.SalesTermRef = {'value': qbo_rel_term.qbo_id}

        lines = []
        for line in self.qbo_invoice_line_ids:
            export_line = line._create_qbo_invoice_line()
            lines.append(export_line)

        qbo_lib_model.Line = lines

        return qbo_lib_model

    def _get_qbo_mapping(self, *args, **kw):
        self.ensure_one()
        qi = self.quickbooks_integration

        return self.qbo_mapping_ids \
            .filtered(
                lambda r: r.qbo_lib_type == self.map_type and r.quickbooks_integration_id == qi
            )

    def apply_qbo_taxes(self):
        self.ensure_one()

        if not self.is_customer_move_type:
            raise ValidationError(_('Invoice must be a customer invoice or refund.'))

        if self.state != 'draft':
            raise UserError(_('Invoice must be in a "Draft" state.'))

        self.quickbooks_integration.ensure_qbo_us_company()

        mapping = self._get_qbo_mapping()
        mapping.ensure_one()

        return mapping.apply_taxes_from_intuit()

    def send_qbo_link(self):
        self.ensure_one()

        if not self.is_customer_move_type:
            raise ValidationError(_('Invoice must be a customer invoice or refund.'))

        if not self.qbo_invoice_link:
            raise ValidationError(_(
                'There is no QuickBooks link in the current invoice. '
                'You should specify customer email address and send it to QuickBooks.'
            ))

        return {
            'name': 'Send QuickBooks Payment Link',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'close_on_report_download': True,
            'context': {
                'active_model': self._name,
                'active_ids': self.ids,
                'default_mail_template_id': self.env.ref('quickbooks_sync_online.email_template_qbo_invoice_link').id,
            },
        }

    def _get_amount_chunks_for_qbo_payments(self, total_amount: float):
        last_index = len(self)

        result = []
        for idx, invoice in enumerate(self, start=1):
            apply_amount = False

            for data in invoice.invoice_payments_widget_content:
                if data.get('account_payment_id') == self.id:
                    apply_amount = data.get('amount')
                    break

            if apply_amount:
                total_amount -= apply_amount
                if idx == last_index and total_amount > 0:
                    apply_amount += total_amount

                result.append((invoice.id, apply_amount))

        return result

    def _get_qbo_department(self):
        if not self.invoice_origin:
            return ''

        warehouse = self.env['sale.order'].search([
            ('name', '=', self.invoice_origin),
            ('company_id', '=', self.company_id.id),
        ], limit=1).warehouse_id

        if not warehouse:
            return ''

        department = warehouse._get_map_instance_or_raise(
            self.quickbooks_integration.id,
            warehouse.map_type,
            raise_if_not_found=False,
        )
        return department.qbo_id or ''

    def _check_qbo_requirements(self, *args, **kw):
        self.ensure_one()

        self._check_type_qbo()
        self._check_currency_qbo()
        self._check_partner_qbo()
        self._check_products_qbo()
        self._check_state_qbo()

        qi = self.quickbooks_integration

        if self.is_vendor_move_type:
            pay_account = self.partner_id.property_account_payable_id

            if not pay_account:
                raise ValidationError(_(
                    '%s: payable account for the vendor "%s" is not set.' % (self.display_name, self.partner_id.name)
                ))

            pay_account.get_qbo_related_account(qi.id)

        if self.invoice_payment_term_id:
            self.invoice_payment_term_id.get_qbo_related_payment_term(qi.id)

        if qi.qb_is_us_company:
            return True

        for line in self.qbo_invoice_line_ids:
            taxes = line.tax_ids
            if taxes:
                taxcode_set = taxes.find_qbo_taxcodes(qi.id, self.qbo_partner_type)

                if not taxcode_set:
                    raise ValidationError(_(
                        'Unable to export Invoice "%s". Cannot find taxcode for the taxes '
                        '"%s". Import all existing taxes first please.'
                        % (self.display_name, str(taxes.mapped('name')))
                    ))

                if len(taxcode_set) > 1:
                    raise ValidationError(_(
                        'Unable to export Invoice "%s". Multiple taxcodes found for the taxes '
                        '"%s". Import all existing taxes first please.'
                        % (self.display_name, str(taxes.mapped('name')))
                    ))

        return True

    def _check_type_qbo(self):
        move_types = self.quickbooks_integration.get_qbo_invoice_allowed_types()
        if self.move_type in move_types:
            return True

        raise ValidationError(
            _('- Unable to export invoice "%s". Unsupported invoice type "%s".') % (self.display_name, self.move_type)
        )

    def _check_currency_qbo(self):
        qi, currency_name, info = self.quickbooks_integration, self.currency_id.name, ''

        if not qi.currency_name_belong_odoo_company(currency_name):
            qbo_company = qi._fetch_qbo_company_info()

            if not qbo_company.multi_currency_enabled:
                info = _(
                    'Multi Currencies are not allowed in your QuickBooks company. '
                    'Change it in settings. Allowed cuurencie(s): %s, requested currency: %s.'
                    % (qbo_company.currency_codes_str(), currency_name)
                )
            elif not qbo_company.validate_foreign_currency(currency_name):
                info = _(
                    'Your QuickBooks company is not supporting the %s currency. Allowed currencies are: %s.'
                    % (currency_name, qbo_company.currency_codes_str())
                )

        if info:
            raise ValidationError(info)

        return True

    def _check_partner_qbo(self):
        partner = self.partner_id
        if not partner:
            raise ValidationError(_(
                '- You need to assign partner to the invoice "%s".' % self.display_name
            ))

        if not partner.is_a_contact_type:
            raise ValidationError(_(
                '- Partner "%s" is not a contact type but "%s".' % (partner.name, partner.type)
            ))

        return True

    def _check_products_qbo(self):
        lines, info = self.qbo_invoice_line_ids, ''

        if self.is_customer_move_type:
            if not all(x.active for x in lines.mapped('product_id')):
                inactive_products = lines.mapped('product_id').filtered(lambda x: not x.active)
                info = _(
                    'Some of the products are archived. Please make them active: %s'
                    % ', '.join(inactive_products.mapped(lambda x: f'{x.display_name} ({x.id})'))
                )
        else:
            if not lines:
                info = _(
                    'You need add products to the "%s" invoice.' % self.display_name
                )
            elif lines.filtered(lambda r: not r.product_id):
                info = _(
                    'Invoice line without a product not allowed for Vendors: "%s".'
                    % self.display_name
                )

        if info:
            raise ValidationError(info)

        return True

    def _check_state_qbo(self):
        if self.state == 'posted':
            return True

        raise ValidationError(_(
            'Confirm invoice "%s" before export please.' % self.display_name
        ))

    def _get_products_to_qbo_export(self):
        qi = self.quickbooks_integration

        if qi.sync_product_as_category:
            products = self.qbo_invoice_line_ids.mapped('product_id.categ_id')
        elif qi.include_product_to_invoice or self.is_vendor_move_type:
            products = self.qbo_invoice_line_ids.mapped('product_id')
        else:
            products = self.env['product.product']

        return products

    def _create_qbo_payment_line(self, amount: float):
        map_invoice = self._get_qbo_mapping()
        map_invoice.ensure_one()

        pay_line_dict = {
            'Amount': amount,
            'LinkedTxn': [{
                'TxnId': map_invoice.qbo_id,
                'TxnType': map_invoice.qbo_entity_name,
            }],
        }
        return [pay_line_dict]

    def to_qbo_json(self):
        self.ensure_one()

        qi = self.quickbooks_integration
        qbo_lib_model = self._prepare_qbo_api_lib_instance(qi.id)

        return self.env['quickbooks.help.wizard'].create_and_run_as_json(
            f'DEBUG: {self.name} [{qbo_lib_model.map_type}]',
            qbo_lib_model.to_dict(),
        )
