# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models

from ..tools import expected_one


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @expected_one
    def get_qbo_related_account(self, qi_id: int):
        return self.env['qbo.map.account'].search([
            ('account_id', '=', self.id),
            ('quickbooks_integration_id', '=', qi_id),
        ])

    def _get_qbo_mapping(self, *args, **kw):
        """It's just a code stub for the 'try_to_map()' method."""
        return False
