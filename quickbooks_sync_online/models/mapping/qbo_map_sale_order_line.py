# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models


class QboMapSaleOrderLine(models.Model):
    _name = 'qbo.map.sale.order.line'
    _inherit = 'qbo.tax.line.abstract'
    _description = 'Qbo Map Sale Order Line'

    order_map_id = fields.Many2one(
        comodel_name='qbo.map.sale.order',
        string='Map Order',
        ondelete='cascade',
    )
