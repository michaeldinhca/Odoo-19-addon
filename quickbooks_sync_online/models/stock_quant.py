# See LICENSE file for full copyright and licensing details.

from odoo import api, models


QTY_TRACKABLE_FIELDS = {
    'lot_id',
    'quantity',
    'reserved_quantity',
    'location_id',
}


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def mark_product_as_is_qbo_update_required(self):
        for company, records in self.grouped('company_id').items():
            qi = company.quickbooks_integration

            if qi.enable_updates_auto_export and qi.qbo_send_stock_property:
                records \
                    .mapped('product_id') \
                    .filtered('qbo_mapping_ids') \
                    .mark_for_qbo_update()

    @api.model_create_multi
    def create(self, vals_list):
        records = super(StockQuant, self).create(vals_list)

        records.mark_product_as_is_qbo_update_required()

        return records

    def write(self, vals):
        result = super(StockQuant, self).write(vals)

        if QTY_TRACKABLE_FIELDS.intersection(set(vals.keys())):
            self.mark_product_as_is_qbo_update_required()

        return result
