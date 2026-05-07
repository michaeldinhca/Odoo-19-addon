# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models

from ..tools import TAXABLE, NON_TAXABLE


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _create_qbo_so_line(self):
        self.ensure_one()

        export_line = {
            'Description': self.name,
            'Amount': self.price_subtotal,
            'DetailType': 'SalesItemLineDetail',
            'SalesItemLineDetail': {
                'Qty': self.product_uom_qty,
                'TaxCodeRef': {
                    'value': TAXABLE if self.product_id.is_qbo_taxable else NON_TAXABLE,
                },
            },
        }

        qi = self.order_id.quickbooks_integration

        if not qi.include_product_to_invoice:
            return export_line

        if qi.sync_product_as_category:
            mapping = self.product_id.categ_id.qbo_mapping_ids
        else:
            mapping = self.product_id.qbo_mapping_ids

        mapping = mapping.filtered(lambda r: r.quickbooks_integration_id == qi)

        export_line['SalesItemLineDetail']['ItemRef'] = {
            'name': mapping.qbo_name,
            'value': mapping.qbo_id,
        }

        return export_line
