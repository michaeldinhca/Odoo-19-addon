# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, fields


class QboMapPaymentMethod(models.Model):
    _name = 'qbo.map.payment.method'
    _inherit = 'qbo.map.abstract'
    _description = 'QuickBooks mapping: PaymentMethod'
    _order = 'sequence'

    _qbo_class_names = ('PaymentMethod',)

    _map_routes = {
        'qbo_name': ('Name', ''),
        'method_type': ('Type', ''),
    }

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    method_type = fields.Char(
        string='Type',
    )

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Odoo Journal',
    )
