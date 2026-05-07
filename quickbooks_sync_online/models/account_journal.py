# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models

from ..tools import expected_one


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @expected_one
    def get_qbo_related_payment_method(self, qi_id: int):
        return self.env['qbo.map.payment.method'].search([
            ('journal_id', '=', self.id),
            ('quickbooks_integration_id', '=', qi_id),
        ], limit=1)
