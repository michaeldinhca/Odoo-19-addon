# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models


class QboTaxLineAbstract(models.AbstractModel):
    _name = 'qbo.tax.line.abstract'
    _description = 'Qbo Tax Line Abstract'

    tax_map_ids = fields.Many2many(
        comodel_name='qbo.map.tax',
        string='Map Taxes',
    )

    line_num = fields.Integer(
        string='Line',
    )

    item_map_id = fields.Many2one(
        comodel_name='qbo.map.product',
        string='Map Product',
    )

    tax_class = fields.Char(
        string='Tax Classification',
    )

    tax_code = fields.Char(
        string='TaxCode Ref',
    )
