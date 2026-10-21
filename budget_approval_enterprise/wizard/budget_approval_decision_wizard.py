from odoo import _, fields, models
from odoo.exceptions import UserError


class BudgetApprovalDecisionWizard(models.TransientModel):
    _name = 'budget.approval.decision.wizard'
    _description = 'Budget Approval Decision'

    budget_ids = fields.Many2many(
        'budget.analytic', 'budget_approval_decision_wizard_rel', 'wizard_id', 'budget_id',
        string="Budgets", required=True)
    decision = fields.Selection(
        [('approve', "Approve"), ('reject', "Reject")], required=True, default='approve')
    note = fields.Text(string="Comment")

    def action_confirm(self):
        self.ensure_one()
        approve = self.decision == 'approve'
        if not approve and not (self.note or '').strip():
            raise UserError(_("A reason is required to reject a budget."))
        done, skipped, failed = [], [], []
        for budget in self.budget_ids:
            if not budget.can_decide_approval:
                skipped.append(budget.display_name)
                continue
            try:
                # One savepoint per budget: a problem on one (e.g. the next step has nobody
                # who can approve it) must not undo the decisions already taken on the others.
                with self.env.cr.savepoint():
                    budget.approval_id.action_decide(approve, self.note)
                done.append(budget.display_name)
            except UserError as exc:
                failed.append("%s: %s" % (budget.display_name, exc.args[0]))
        if not done and len(self.budget_ids) == 1 and failed:
            raise UserError(failed[0])
        if not done:
            raise UserError("\n".join(
                [_("None of the selected budgets is waiting for your decision.")] + failed))
        message = _("%(count)s budget(s) %(verb)s.", count=len(done),
                    verb=_("approved") if approve else _("rejected"))
        if skipped:
            message += " " + _("Skipped, not waiting for you: %s.", ", ".join(skipped))
        if failed:
            message += " " + _("Not processed: %s.", " | ".join(failed))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Budget approval"),
                'message': message,
                'type': 'warning' if (skipped or failed) else 'success',
                'sticky': bool(skipped or failed),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
