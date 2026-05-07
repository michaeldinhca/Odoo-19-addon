# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, fields


class QboMapTerm(models.Model):
    _name = 'qbo.map.term'
    _inherit = 'qbo.map.abstract'
    _description = 'QuickBooks mapping: Term'

    _qbo_class_names = ('Term',)

    _map_routes = {
        'qbo_name': ('Name', ''),
    }

    term_id = fields.Many2one(
        comodel_name='account.payment.term',
        string='Odoo PaymentTerm',
    )
