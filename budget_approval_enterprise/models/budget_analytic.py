from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

# Header content that decides which rule applies. The lines themselves are guarded one by one
# in budget.line, so only edits that change an amount are blocked, not zero-amount additions.
APPROVAL_LOCKED_FIELDS = {'budget_type', 'company_id'}


class BudgetAnalytic(models.Model):
    _inherit = 'budget.analytic'

    approval_ids = fields.One2many('budget.approval', 'budget_id', string="Approvals", readonly=True)
    approval_step_ids = fields.One2many(related='approval_ids.step_ids', string="Approval Steps")
    approval_id = fields.Many2one('budget.approval', compute='_compute_approval_id', string="Latest Approval")
    approval_state = fields.Selection(
        [('none', "Not Requested"), ('to_approve', "To Approve"),
         ('approved', "Approved"), ('rejected', "Rejected")],
        compute='_compute_approval_state', store=True, default='none', string="Approval Status")
    approval_required = fields.Boolean(compute='_compute_approval_required')
    pending_approver_ids = fields.Many2many('res.users', compute='_compute_pending_approver')
    can_decide_approval = fields.Boolean(compute='_compute_pending_approver')

    @api.depends('approval_ids')
    def _compute_approval_id(self):
        for budget in self:
            budget.approval_id = budget.approval_ids.sorted('id')[-1:]

    @api.depends('approval_ids.state')
    def _compute_approval_state(self):
        mapping = {'in_progress': 'to_approve', 'approved': 'approved', 'rejected': 'rejected'}
        for budget in self:
            latest = budget.approval_ids.sorted('id')[-1:]
            budget.approval_state = mapping.get(latest.state, 'none')

    @api.depends('state', 'budget_type', 'company_id', 'budget_line_ids.budget_amount')
    def _compute_approval_required(self):
        Rule = self.env['budget.approval.rule']
        for budget in self:
            budget.approval_required = bool(
                budget.state == 'draft' and budget.company_id and Rule._get_matching_rule(budget))

    @api.depends('approval_ids.step_ids.state', 'approval_ids.state',
                 'approval_ids.step_ids.approver_ids', 'approval_ids.step_ids.approved_by_ids')
    @api.depends_context('uid')
    def _compute_pending_approver(self):
        for budget in self:
            latest = budget.approval_ids.sorted('id')[-1:]
            step = latest.step_ids.filtered(lambda s: s.state == 'pending')[:1]
            # people of the step who still have to act (those who already approved are done)
            waiting = step.approver_ids - step.approved_by_ids
            budget.pending_approver_ids = waiting
            budget.can_decide_approval = bool(
                step and latest.state == 'in_progress' and self.env.user in waiting)

    def _approval_total_amount(self):
        self.ensure_one()
        return sum(abs(amount) for amount in self.budget_line_ids.mapped('budget_amount'))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_request_approval(self):
        self.check_access('write')
        for budget in self:
            if budget.state != 'draft':
                raise UserError(_("Only a draft budget can be sent for approval."))
            if budget.approval_state in ('to_approve', 'approved'):
                raise UserError(_("This budget already has an active approval."))
            rule = self.env['budget.approval.rule']._get_matching_rule(budget)
            if not rule:
                raise UserError(_("No approval rule applies to this budget, it can be opened directly."))
            budget._check_rule_has_approvers(rule)
            self.env['budget.approval']._create_for_budget(budget, rule)

    def _check_rule_has_approvers(self, rule):
        """Refuse the request upfront when a step could never be approved (requester excluded)."""
        self.ensure_one()
        for step in rule.step_ids:
            holders = self.env['budget.approval.rule.step']._approvers_for(
                step.job_ids, self.company_id, exclude=self.env.user)
            if not holders:
                raise UserError(_(
                    "Nobody can approve step \"%(step)s\": no employee of %(company)s other than you "
                    "holds %(jobs)s. Check the job positions and the employees' linked users.",
                    step=step.name or step.sequence, company=self.company_id.name,
                    jobs=", ".join(step.job_ids.mapped('name'))))
            if step.approval_mode == 'count' and len(holders) < step.required_count:
                raise UserError(_(
                    "Step \"%(step)s\" needs %(needed)s approvals but only %(found)s people other than you "
                    "hold %(jobs)s in %(company)s.",
                    step=step.name or step.sequence, needed=step.required_count, found=len(holders),
                    jobs=", ".join(step.job_ids.mapped('name')), company=self.company_id.name))

    def action_withdraw_approval(self):
        for budget in self:
            approval = budget.approval_id
            if approval.state not in ('in_progress', 'approved') or budget.state != 'draft':
                raise UserError(_("There is no approval to withdraw or reset."))
            if (approval.submitted_by != self.env.user
                    and not self.env.user.has_group('account.group_account_manager')):
                raise UserError(_(
                    "Only the requester or an accounting manager can withdraw or reset the approval."))
            if approval.state == 'in_progress':
                approval.sudo()._finish('withdrawn', _("Approval withdrawn by %s.", self.env.user.name))
            else:
                approval.sudo()._finish('voided', _(
                    "Approval reset by %s, budgeted amounts can be changed again.", self.env.user.name))

    def _action_approval_decision(self, decision):
        """Open the decision wizard for one budget (form buttons) or many (list actions)."""
        return {
            'type': 'ir.actions.act_window',
            'name': _("Approve Budgets") if decision == 'approve' else _("Reject Budgets"),
            'res_model': 'budget.approval.decision.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_budget_ids': self.ids, 'default_decision': decision},
        }

    def action_approval_approve(self):
        return self._action_approval_decision('approve')

    def action_approval_reject(self):
        return self._action_approval_decision('reject')

    # ------------------------------------------------------------------
    # Gate and lock
    # ------------------------------------------------------------------
    def _approval_gate_error(self):
        """Reason why this draft budget may not be opened yet, or False."""
        self.ensure_one()
        latest = self.approval_ids.sorted('id')[-1:]
        if latest.state == 'in_progress':
            return _("This budget is waiting for approval from %s.",
                     ", ".join(self.pending_approver_ids.mapped('name')))
        rule = self.env['budget.approval.rule']._get_matching_rule(self)
        if not rule:
            return False
        if latest.state == 'approved':
            rounding = self.company_id.currency_id.rounding
            if float_compare(latest.amount, self._approval_total_amount(), precision_rounding=rounding) == 0:
                return False
            return _("The budgeted amount changed after approval. Request approval again.")
        if latest.state == 'rejected':
            return _("This budget was rejected. Review it and request approval again.")
        return _("This budget requires approval before it can be opened. Use Request Approval.")

    def _approval_on_content_change(self):
        for budget in self.filtered(lambda b: b.state == 'draft'):
            latest = budget.approval_ids.sorted('id')[-1:]
            if latest.state == 'in_progress':
                raise UserError(_(
                    "Budgeted amounts are frozen while this budget waits for approval. "
                    "Withdraw the approval to change them."))
            if latest.state == 'approved':
                raise UserError(_(
                    "Budgeted amounts are frozen once the budget is approved. "
                    "Use Reset Approval to change them, then request approval again."))

    def unlink(self):
        # Close running approvals first so their activities can be removed with the budget.
        for approval in self.approval_ids.filtered(lambda a: a.state == 'in_progress'):
            approval.sudo()._finish('voided')
        return super().unlink()

    def write(self, vals):
        if not self.env.context.get('budget_approval_bypass'):
            if vals.get('state') == 'confirmed':
                for budget in self.filtered(lambda b: b.state == 'draft'):
                    error = budget._approval_gate_error()
                    if error:
                        raise UserError(error)
            if APPROVAL_LOCKED_FIELDS & vals.keys():
                self._approval_on_content_change()
        res = super().write(vals)
        new_state = vals.get('state')
        if new_state == 'draft':
            # Back to draft: a past approval must not authorize a later Open.
            for approval in self.approval_ids.filtered(lambda a: a.state in ('approved', 'in_progress')):
                approval.sudo()._finish('expired', _("The budget returned to draft, its approval expired."))
        elif new_state == 'canceled':
            for approval in self.approval_ids.filtered(lambda a: a.state == 'in_progress'):
                approval.sudo()._finish('voided', _("The budget was cancelled, its approval was voided."))
        return res
