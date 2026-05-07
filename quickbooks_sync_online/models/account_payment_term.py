# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models

from ..tools import expected_one


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    @expected_one
    def get_qbo_related_payment_term(self, qi_id: int):
        return self.env['qbo.map.term'].search([
            ('term_id', '=', self.id),
            ('quickbooks_integration_id', '=', qi_id),
        ])
