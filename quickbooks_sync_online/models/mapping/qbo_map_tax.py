# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class QboMapTax(models.Model):
    _name = 'qbo.map.tax'
    _inherit = [
        'qbo.map.abstract',
        'qbo.map.automapping.mixin',
    ]
    _description = 'QuickBooks mapping: TaxRate'

    _related_odoo_field = 'tax_id'
    _qbo_class_names = ('TaxRate',)

    _map_routes = {
        'qbo_name': ('Name', ''),
    }
    _odoo_routes = {
        'active': ('Active', True),
        'name': ('Name', ''),
        'amount': ('RateValue', 0),
    }

    tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Odoo Tax',
        domain="[('company_id', '=', company_id)]",
    )

    type_tax_use = fields.Selection(
        string='Odoo Tax Type',
        related='tax_id.type_tax_use',
    )

    def _adjust_odoo_values(self, values):
        res = super(QboMapTax, self)._adjust_odoo_values(values)

        res.update({
            'type_tax_use': 'sale',  # Currently only customer-based taxes.
            'company_id': self.company_id.id,
            'description': '%.2f' % res['amount'] + '%',
            'price_include': False,
            'include_base_amount': False,
            'is_base_affected': False,
        })

        return res

    def _update_odoo_search_domain(self):
        domain_list = super()._update_odoo_search_domain()

        domain_list[0].extend([
            ('type_tax_use', '=', 'sale'),  # Currently only customer-based taxes.
            ('company_id', '=', self.company_id.id),
            ('amount', '=', self.qbo_dict_body.get('RateValue', False)),
        ])

        return domain_list

    def find_taxcodes(self, partner_type: str, raise_error: bool = False):
        self.ensure_one()

        search_field = 'sales_tax_rate_ids' if (partner_type == 'customer') else 'purchase_tax_rate_ids'

        taxcodes = self.env['qbo.map.taxcode'].search([
            (search_field, 'in', self.ids),
            ('quickbooks_integration_id', '=', self.quickbooks_integration_id.id),
        ]).mapped('qbo_id')

        if not taxcodes and raise_error:
            raise ValidationError(_(
                'Cannot find taxcode for the tax-mapping "%s" (id=%s). '
                'Import all existing taxcodes first please.' % (self.display_name, self.id)
            ))

        return taxcodes

    def fetch_resource_data_from_qbo(self, qi_id: int, *args, **kw):
        qi = self.env['quickbooks.integration'].browse(qi_id)

        return self \
            .with_context(company_id=qi.company_id.id) \
            .with_delay(
                description=f'Import Taxes from QuickBooks',
                channel=self.job_channel,
            ).get_taxes_from_qbo(qi_id)

    def get_taxes_from_qbo(self, qi_id: int):
        self._fetch_resource_data_from_qbo(qi_id, self.map_type)

        Taxcode = self.env['qbo.map.taxcode']
        Taxcode._fetch_resource_data_from_qbo(qi_id, Taxcode.map_type)
