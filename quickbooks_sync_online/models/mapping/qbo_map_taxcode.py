# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, fields


class QboMapTaxcode(models.Model):
    _name = 'qbo.map.taxcode'
    _inherit = 'qbo.map.abstract'
    _description = 'QuickBooks mapping: TaxCode'

    _qbo_class_names = ('TaxCode',)
    _map_routes = {
        'qbo_name': ('Name', ''),
        'sales_tax_rate_ids.raw': ('SalesTaxRateList.TaxRateDetail', []),
        'purchase_tax_rate_ids.raw': ('PurchaseTaxRateList.TaxRateDetail', []),
    }

    sales_tax_rate_ids = fields.Many2many(
        comodel_name='qbo.map.tax',
        relation='qbo_map_sale_taxcode_taxrate_rel',
        column1='taxcode_id',
        column2='taxrate_id',
        string='Sales QuickBooks Taxes',
    )
    purchase_tax_rate_ids = fields.Many2many(
        comodel_name='qbo.map.tax',
        relation='qbo_map_purchase_taxcode_taxrate_rel',
        column1='taxcode_id',
        column2='taxrate_id',
        string='Purchase QuickBooks Taxes',
    )

    def _adjust_mapping_values(self, qi_id: int, values: dict, qbo_lib_model) -> dict:
        res = super(QboMapTaxcode, self)._adjust_mapping_values(qi_id, values, qbo_lib_model)

        # 1. map sales tax rates
        sales_tax_rate_ids = []
        for data in (values['sales_tax_rate_ids']['raw'] or []):
            qbo_id = data['TaxRateRef']['value']

            tax_map = self.env['qbo.map.tax'].search([
                ('qbo_id', '=', qbo_id),
                ('quickbooks_integration_id', '=', qi_id),
            ], limit=1)

            if tax_map:
                sales_tax_rate_ids.append(tax_map.id)

        res['sales_tax_rate_ids'] = [(6, 0, sales_tax_rate_ids)]

        # 2. map purchase tax rates
        purchase_tax_rate_ids = []
        for data in (values['purchase_tax_rate_ids']['raw'] or []):
            qbo_id = data['TaxRateRef']['value']

            tax_map = self.env['qbo.map.tax'].search([
                ('qbo_id', '=', qbo_id),
                ('quickbooks_integration_id', '=', qi_id),
            ], limit=1)

            if tax_map:
                purchase_tax_rate_ids.append(tax_map.id)

        res['purchase_tax_rate_ids'] = [(6, 0, purchase_tax_rate_ids)]

        return res
