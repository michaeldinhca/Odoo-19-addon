# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models


class QboMapAccount(models.Model):
    _name = 'qbo.map.account'
    _inherit = [
        'qbo.map.abstract',
        'qbo.map.automapping.mixin',
    ]
    _description = 'QuickBooks mapping: Account'

    _related_odoo_field = 'account_id'
    _qbo_class_names = ('Account',)

    _map_routes = {
        'qbo_name': ('Name', ''),
        'account_type': ('AccountType', ''),
        'account_sub_type': ('AccountSubType', ''),
        'classification': ('Classification', ''),
    }

    account_type = fields.Char(
        string='Account type',
        readonly=True,
    )

    account_sub_type = fields.Char(
        string='Account subtype',
        readonly=True,
    )

    classification = fields.Char(
        string='Classification',
        readonly=True,
    )

    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Odoo Account',
        domain="[('company_ids', 'in', company_id)]",
    )

    def _update_odoo_search_domain(self):
        domain_list = super()._update_odoo_search_domain()

        domain_list[0].append(
            ('company_ids', 'in', self.company_id.id)
        )
        return domain_list
