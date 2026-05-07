# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, fields


class QboMapDepartment(models.Model):
    _name = 'qbo.map.department'
    _inherit = [
        'qbo.map.abstract',
        'qbo.map.update.mixin',
    ]
    _description = 'QuickBooks mapping: Department'

    _related_odoo_field = 'warehouse_id'
    _qbo_class_names = ('Department',)

    _map_routes = {
        'qbo_name': ('Name', ''),
    }

    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Odoo Warehouse',
    )

    is_sub_department = fields.Boolean(
        string='Is Sub Department',
    )
