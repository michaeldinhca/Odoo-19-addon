# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models


class QboMapInvoiceLine(models.Model):
    _name = 'qbo.map.invoice.line'
    _inherit = 'qbo.tax.line.abstract'
    _description = 'Qbo Map Invoice Line'

    invoice_map_id = fields.Many2one(
        comodel_name='qbo.map.account.move',
        string='Map Invoice',
        ondelete='cascade',
    )
