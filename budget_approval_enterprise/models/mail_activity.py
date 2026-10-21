from odoo import _, models
from odoo.exceptions import UserError

# Context key used by this module's own code (decision, withdraw, void) to complete or
# delete an approval activity without re-triggering the guards below on itself.
SKIP_KEY = 'budget_approval_skip_intercept'


class MailActivity(models.Model):
    """Keep the To-Do of an approval step tied to the approval record.

    Without this, ticking the To-Do as done in the chatter would close the activity but leave the
    approval waiting. Completing it now opens the decision dialog instead.
    """
    _inherit = 'mail.activity'

    def _budget_approval_pending_steps(self):
        return self.env['budget.approval.step'].sudo().search([
            ('activity_ids', 'in', self.ids), ('state', '=', 'pending'),
        ])

    def _budget_approval_activities(self):
        """Subset of self that belongs to a pending approval step."""
        steps = self._budget_approval_pending_steps()
        return self.filtered(lambda a: a.id in steps.activity_ids.ids)

    def action_done(self):
        """Raw Mark Done (list, header, edit dialog): open the Approve/Reject dialog instead."""
        active_self = self.filtered(lambda a: a.active)
        mine = active_self._budget_approval_activities()
        rest = active_self - mine
        result = super(MailActivity, rest).action_done() if rest else True
        if mine:
            if len(mine) > 1:
                raise UserError(_("Please act on budget approval activities one at a time."))
            step = mine._budget_approval_pending_steps()[:1]
            return step.approval_id.budget_id._action_approval_decision('approve')
        return result

    def _action_done(self, feedback=False, attachment_ids=None):
        """The chatter's inline Done box ends up here and bypasses action_done(). Block it: a
        decision is approve or reject, which free-text feedback cannot tell."""
        if not self.env.context.get(SKIP_KEY) and self._budget_approval_activities():
            raise UserError(_(
                "Use the Approve or Reject buttons on the budget to act on this activity."))
        return super()._action_done(feedback=feedback, attachment_ids=attachment_ids)

    def unlink(self):
        if not self.env.context.get(SKIP_KEY) and self._budget_approval_activities():
            raise UserError(_(
                "This activity belongs to a pending budget approval. Use Approve, Reject or "
                "Withdraw Approval on the budget instead of deleting it."))
        return super().unlink()
