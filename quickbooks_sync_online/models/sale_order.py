# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import fields, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = [
        'sale.order',
        'quickbooks.mapping.mixin',
        'quickbooks.export.mixin',
    ]

    qbo_mapping_ids = fields.One2many(
        comodel_name='qbo.map.sale.order',
        inverse_name='order_id',
        readonly=True,
    )

    def get_qbo_taxes_from_salereceipt(self):
        self.ensure_one()

        company = self.company_id
        company.raise_if_no_qbo_auth()
        qi = company.quickbooks_integration

        self._check_qbo_requirements()

        # Export main partner if no mapping found
        partner = self.partner_id._ensure_qbo_currency(self)
        partner_mapping = partner._get_qbo_mapping(qi.id, 'customer')

        if not partner_mapping:
            partner_mapping = partner.export_qbo_one(qi.id, 'customer')

        partner_mapping.ensure_one()

        # 1. Tax exempt customer flow
        if not partner_mapping.is_intuit_taxable_customer():
            self.order_line.filtered('product_id') \
                .write({'tax_ids': [(6, 0, [])]})

            _logger.info(
                'The customer "%s" (qbo_id=%s) is tax exempt.',
                partner_mapping.qbo_name,
                partner_mapping.qbo_id,
            )

            return []

        # 2. Taxable customer flow: export sales order and get taxes from response
        mapping = self.export_qbo_one()

        result = mapping.apply_taxes_from_intuit()

        # Delete the sales order from QuickBooks after taxes are applied
        mapping.delete_qbo_one_with_delay()

        return result

    def export_qbo_one(self):
        self.ensure_one()

        qi = self.quickbooks_integration
        self = self.with_company(qi.company_id)

        # Check requirements
        self._check_qbo_requirements()

        # Export customer if no mapping found
        partner = self.partner_id._ensure_qbo_currency(self)
        partner_mapping = partner._get_qbo_mapping(qi.id, 'customer')

        if not partner_mapping:
            partner_mapping = partner.export_qbo_one(qi.id, 'customer')
        partner_mapping.ensure_one()

        # Export products if no mapping found
        products = self._get_products_to_qbo_export()
        for product in products:
            product_mapping = product._get_qbo_mapping(qi.id, 'item')

            if not product_mapping:
                product_mapping = product.export_qbo_one(qi.id)
            product_mapping.ensure_one()

        # Prepare sales-order qbo-lib instance
        qbo_lib_model = self._prepare_qbo_api_lib_instance(qi.id)

        # Export sales-order
        mapping = self._export_qbo_one(qi.id, qbo_lib_model)

        return mapping

    def _prepare_qbo_api_lib_instance(self, qi_id: int):
        qbo_lib_model = self._init_qbo_lib_instance(self.map_type)

        partner = self.partner_id._ensure_qbo_currency(self)
        partner_mapping = partner._get_qbo_mapping(qi_id, 'customer')

        qbo_lib_model.CustomerRef = {'value': partner_mapping.qbo_id}
        qbo_lib_model.CurrencyRef = {'value': self.partner_id.currency_id.name}

        ship_address = self.partner_shipping_id._format_to_qbo_address()

        qbo_lib_model.ShipAddr = ship_address

        lines = []
        for line in self.order_line.filtered('product_id'):
            export_line = line._create_qbo_so_line()
            lines.append(export_line)

        qbo_lib_model.Line = lines

        return qbo_lib_model

    def _check_qbo_requirements(self, *args, **kw):
        # Check state
        if self.state != 'draft':
            raise UserError(_('The sales order "%s" have to be in a "Draft" state.') % self.display_name)

        qi = self.company_id.quickbooks_integration
        qi.ensure_qbo_us_company()

        # Check currency
        currency_name = self.currency_id.name
        if not qi.currency_name_belong_odoo_company(currency_name):
            qbo_company = qi._fetch_qbo_company_info()

            info = ''
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
                raise UserError(info)

        # Check products
        products = self._get_products_to_qbo_export()
        if not products:
            raise UserError(_('The sales order "%s" must contain products.') % self.display_name)

    def _get_products_to_qbo_export(self):
        qi = self.quickbooks_integration

        if qi.sync_product_as_category:
            products = self.mapped('order_line.product_id.categ_id')
        elif qi.include_product_to_invoice:
            products = self.mapped('order_line.product_id')
        else:
            products = self.env['product.product']

        return products
