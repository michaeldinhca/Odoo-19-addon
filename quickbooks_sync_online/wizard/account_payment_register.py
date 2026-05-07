# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payments(self):
        payments = super()._create_payments()

        if self.env.context.get('mark_as_excluded_from_qbo_sync'):
            payments.mark_excluded_from_qbo_sync()

        # Run compute manually to force assign reconciled invoices to the payments
        payments._compute_stat_buttons_from_reconciliation()

        for payment in payments.filtered(lambda x: not x.is_excluded_from_qbo_sync):
            qi = payment.company_id.quickbooks_integration
            if qi.qb_access_granted and qi.enable_payments_sync_out:
                payment.with_company(qi.company_id).action_export_to_quickbooks()

        return payments
