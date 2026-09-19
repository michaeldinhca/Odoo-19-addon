from odoo import models


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    def unlink(self):
        if not self:
            return True
        # Stamp the ownership trail (who, when, through which path) before the partial disappears.
        # The foreign key on the trail is "set null", so the trail row itself is kept.
        # sudo: end users have no access to the ownership trail; this is a read of our own audit table.
        rows = self.env['enterprise.remittance.reconciliation'].sudo().search([('partial_id', 'in', self.ids)])
        if rows:
            rows._remittance_mark_removed(self.env.context.get('remittance_removal_via') or 'external')
        result = super().unlink()
        if rows:
            rows.invalidate_recordset(['partial_id'])
        return result
