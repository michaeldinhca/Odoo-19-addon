from odoo import models


class AccountMove(models.Model):
    """Second line of defence for the controlled reset / cancel / delete of a payment.

    The payment methods are guarded first (see account.payment._remittance_guard). These overrides cover
    the same operations attempted directly on the payment's journal entry, so the controls cannot be
    bypassed by going through the journal entry form instead of the payment form.
    """
    _inherit = 'account.move'

    def _remittance_guard_payment_moves(self, operation):
        entries = self.filtered(lambda move: move.move_type == 'entry')
        if not entries:
            return
        # sudo: existence lookup only, so users without direct access to payments are not blocked by an AccessError.
        payments = self.env['account.payment'].sudo().search([('move_id', 'in', entries.ids)])
        if payments:
            payments.with_env(self.env)._remittance_guard(operation)

    def button_draft(self):
        self._remittance_guard_payment_moves('draft')
        return super().button_draft()

    def button_cancel(self):
        self._remittance_guard_payment_moves('cancel')
        return super().button_cancel()

    def unlink(self):
        self._remittance_guard_payment_moves('delete')
        return super().unlink()
