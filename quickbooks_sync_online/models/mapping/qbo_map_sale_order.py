# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models

from ...quickbooks_api import ObjectNotFoundException


class QboMapSaleOrder(models.Model):
    _name = 'qbo.map.sale.order'
    _inherit = [
        'qbo.map.abstract',
        'qbo.map.tax.mixin',
    ]
    _description = 'QuickBooks mapping: SalesReceipt'

    _related_odoo_field = 'order_id'
    _qbo_class_names = ('SalesReceipt',)

    _map_routes = {
        'qbo_name': ('DocNumber', ''),
        'total_tax': ('TxnTaxDetail.TotalTax', ''),
    }

    order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Odoo Sale Order',
        domain='[("company_id", "=", company_id)]',
    )
    partner_id = fields.Many2one(
        related='order_id.partner_id',
    )
    qbo_tax_ids = fields.Many2many(
        comodel_name='qbo.map.tax',
        string='QuickBooks Taxes',
    )
    total_tax = fields.Char(
        string='Total Tax',
    )
    order_map_line_ids = fields.One2many(
        comodel_name='qbo.map.sale.order.line',
        inverse_name='order_map_id',
        string='Map Order Lines',
    )

    def action_delete_in_qbo(self):
        for record in self:
            record.delete_qbo_one_with_delay()

    def delete_qbo_one_with_delay(self):
        self.ensure_one()

        job_kwargs = {
            'identity_key': f'delete_qbo_salesreceipt-{self}',
            'description': '[Technical] %s: Delete QuickBooks SalesReceipt (id=%s)' % (self.qbo_name, self.qbo_id),
            'channel': self.job_channel,
        }

        self \
            .with_context(company_id=self.company_id.id) \
            .with_delay(**job_kwargs).delete_qbo_one()

    def delete_qbo_one(self):
        self.ensure_one()

        try:
            value = super().delete_qbo_one()
        except ObjectNotFoundException:
            value = True

        return value

    def create_qbo_mapping_from_response(self, qbo_lib_model, qi_id: int, odoo_id: int = None):
        mapping = super().create_qbo_mapping_from_response(qbo_lib_model, qi_id, odoo_id=odoo_id)

        vals_list = mapping._prepare_map_lines(qbo_lib_model)
        self.env['qbo.map.sale.order.line'].create(vals_list)

        return mapping

    def apply_taxes_from_intuit(self):
        self.ensure_one()

        for tax in self.qbo_tax_ids.filtered(lambda r: not r.tax_id):
            tax.sudo().try_to_map(summary=False)

        zipper = zip(
            self.order_id.order_line.filtered('product_id'),
            self.order_map_line_ids,
        )

        lines = []
        for so_line, map_line in zipper:
            taxes = map_line.tax_map_ids.mapped('tax_id')

            lines.append(
                (1, so_line.id, {'tax_ids': [(6, 0, taxes.ids)]}),
            )

        return self.order_id \
            .write({'order_line': lines})

    def _adjust_mapping_values(self, qi_id: int, values: dict, qbo_lib_model) -> dict:
        res = super(QboMapSaleOrder, self)._adjust_mapping_values(qi_id, values, qbo_lib_model)

        map_tax = self._parse_map_tax_ids(qi_id, qbo_lib_model.TxnTaxDetail)
        res['qbo_tax_ids'] = [(6, 0, map_tax.ids)]

        return res

    def _prepare_map_lines(self, qbo_lib_model):
        res = super(QboMapSaleOrder, self)._prepare_map_lines(qbo_lib_model)

        for data in res:
            data['order_map_id'] = self.id

        return res
