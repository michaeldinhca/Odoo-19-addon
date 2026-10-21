from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BudgetApproval(models.Model):
    """One submission episode of a budget. Steps are an immutable snapshot of the rule."""
    _name = 'budget.approval'
    _description = 'Budget Approval (Submission)'
    _order = 'id desc'

    budget_id = fields.Many2one('budget.analytic', required=True, ondelete='cascade', index=True)
    # related/stored so this model can carry its own ir.rule (the budget's own
    # multi-company rule does not extend to this separate model).
    company_id = fields.Many2one(related='budget_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    rule_id = fields.Many2one('budget.approval.rule', ondelete='set null', readonly=True)
    state = fields.Selection(
        [('in_progress', "In Progress"), ('approved', "Approved"), ('rejected', "Rejected"),
         ('withdrawn', "Withdrawn"), ('voided', "Voided"), ('expired', "Expired")],
        default='in_progress', required=True, readonly=True)
    amount = fields.Monetary(
        string="Budgeted Amount", currency_field='currency_id', readonly=True,
        help="Total budgeted amount at submission, compared again when the budget is opened.")
    submitted_by = fields.Many2one('res.users', readonly=True)
    submitted_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    step_ids = fields.One2many('budget.approval.step', 'approval_id', string="Steps")

    def _create_for_budget(self, budget, rule):
        # sudo(): this model has no write/create ACL for anyone, creation is an internal
        # side effect of a request already authorized by action_request_approval().
        approval = self.sudo().create({
            'budget_id': budget.id,
            'rule_id': rule.id,
            'amount': budget._approval_total_amount(),
            'submitted_by': self.env.uid,
            'submitted_at': fields.Datetime.now(),
            'step_ids': [(0, 0, {
                'sequence': s.sequence,
                'name': s.name or _("Step %s", i),
                'job_ids': [(6, 0, s.job_ids.ids)],
                'approval_mode': s.approval_mode,
                'required_count': s.required_count,
            }) for i, s in enumerate(rule.step_ids.sorted(lambda s: (s.sequence, s.id)), start=1)],
        })
        budget.sudo().message_post(body=_(
            "Approval requested by %(user)s (rule: %(rule)s). Approval chain: %(chain)s.",
            user=self.env.user.name, rule=rule.name,
            chain=" > ".join("%s (%s)" % (st.name, ", ".join(st.job_ids.mapped('name')))
                             for st in approval.step_ids.sorted('sequence'))))
        approval._activate_next()
        return approval

    def _activate_next(self):
        self.ensure_one()
        step = self.step_ids.filtered(lambda s: s.state == 'waiting').sorted(lambda s: (s.sequence, s.id))[:1]
        if not step:
            self._finish('approved')
            return
        step._activate()
        self.budget_id.sudo().message_post(body=_(
            "Waiting for approval from %(approvers)s (%(step)s: %(needs)s).",
            approvers=", ".join(step.approver_ids.mapped('name')), step=step.name,
            needs=step.needs_label))

    def action_decide(self, approve, note=None):
        """Decision of the pending step. Only the user assigned to it may decide."""
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_("This approval is no longer in progress."))
        step = self.step_ids.filtered(lambda s: s.state == 'pending')[:1]
        if not step:
            raise UserError(_("There is no step waiting for a decision."))
        if self.env.user not in step.approver_ids:
            raise UserError(_(
                "Only an employee holding %(jobs)s can approve or reject this step.",
                jobs=", ".join(step.job_ids.mapped('name'))))
        if approve and self.env.user in step.approved_by_ids:
            raise UserError(_("You already approved this step."))
        budget = self.budget_id.sudo()
        step = step.sudo()
        # sudo(): mutations of this model go through this guarded method only (see ACL).
        if approve:
            step.approved_by_ids = [(4, self.env.user.id)]
            step._clear_activity(self.env.user)
            remaining = step.required_approvals - len(step.approved_by_ids)
            if remaining > 0:
                budget.message_post(body=_(
                    "%(user)s approved %(step)s (%(done)s of %(needed)s approvals).%(note)s",
                    user=self.env.user.name, step=step.name, done=len(step.approved_by_ids),
                    needed=step.required_approvals, note=_(" Comment: %s", note) if note else ""))
                return
            step.write({
                'state': 'approved', 'decided_at': fields.Datetime.now(),
                'decided_by': self.env.user.id, 'note': note or False,
            })
            step._clear_activity()
            budget.message_post(body=_(
                "%(user)s approved %(step)s, step complete (%(done)s of %(needed)s approvals).%(note)s",
                user=self.env.user.name, step=step.name, done=len(step.approved_by_ids),
                needed=step.required_approvals, note=_(" Comment: %s", note) if note else ""))
            self.sudo()._activate_next()
        else:
            step.write({
                'state': 'rejected', 'decided_at': fields.Datetime.now(),
                'decided_by': self.env.user.id, 'note': note or False,
            })
            step._clear_activity()
            budget.message_post(body=_(
                "%(user)s rejected the budget at %(step)s. Reason: %(note)s",
                user=self.env.user.name, step=step.name, note=note or "-"))
            self.sudo()._finish('rejected')

    def _finish(self, state, reason=None):
        """Close the approval in a final state, cancel open steps and clean their activities."""
        for approval in self:
            open_steps = approval.step_ids.filtered(lambda s: s.state in ('waiting', 'pending'))
            open_steps._clear_activity()
            open_steps.write({'state': 'cancelled'})
            approval.write({'state': state, 'completed_at': fields.Datetime.now()})
            if state == 'approved':
                approval.budget_id.message_post(body=_("Budget fully approved. It can now be opened."))
            elif reason:
                approval.budget_id.message_post(body=reason)


class BudgetApprovalStep(models.Model):
    _name = 'budget.approval.step'
    _description = 'Budget Approval Step'
    _order = 'approval_id, sequence, id'

    approval_id = fields.Many2one('budget.approval', required=True, ondelete='cascade', index=True)
    budget_id = fields.Many2one(related='approval_id.budget_id', store=True, index=True)
    company_id = fields.Many2one(related='approval_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    job_ids = fields.Many2many(
        'hr.job', 'budget_approval_step_job_rel', 'step_id', 'job_id',
        string="Job Positions", readonly=True)
    approver_ids = fields.Many2many(
        'res.users', 'budget_approval_step_approver_rel', 'step_id', 'user_id',
        string="Approvers", readonly=True,
        help="Holders of the positions when the step became active.")
    approval_mode = fields.Selection(
        [('any', "Any one of them"), ('all', "All of them"), ('count', "At least N of them")],
        required=True, default='any', readonly=True)
    required_count = fields.Integer(readonly=True)
    required_approvals = fields.Integer(
        readonly=True, help="Approvals needed to complete the step, fixed when the step became active.")
    approved_by_ids = fields.Many2many(
        'res.users', 'budget_approval_step_approved_rel', 'step_id', 'user_id',
        string="Approved By", readonly=True)
    needs_label = fields.Char(compute='_compute_needs_label', string="Needs")
    eligible_approver_ids = fields.Many2many(
        'res.users', compute='_compute_eligible_approver_ids', string="Can Approve",
        help="Users who can approve this step: the current holders of its job positions "
             "(requester excluded). Fixed once the step has become active.")
    decided_by = fields.Many2one('res.users', readonly=True)
    state = fields.Selection(
        [('waiting', "Waiting"), ('pending', "To Approve"), ('approved', "Approved"),
         ('rejected', "Rejected"), ('cancelled', "Cancelled")],
        default='waiting', required=True, readonly=True)
    decided_at = fields.Datetime(readonly=True)
    note = fields.Text(readonly=True)
    activity_ids = fields.Many2many(
        'mail.activity', 'budget_approval_step_activity_rel', 'step_id', 'activity_id', readonly=True)

    @api.depends('state', 'job_ids', 'approver_ids', 'approval_id.submitted_by', 'company_id')
    def _compute_eligible_approver_ids(self):
        Step = self.env['budget.approval.rule.step']
        for step in self:
            if step.state == 'waiting':
                step.eligible_approver_ids = Step._approvers_for(
                    step.job_ids, step.company_id, exclude=step.approval_id.submitted_by)
            else:
                step.eligible_approver_ids = step.approver_ids

    @api.depends('approval_mode', 'required_count', 'required_approvals', 'state',
                 'eligible_approver_ids', 'approved_by_ids')
    def _compute_needs_label(self):
        for step in self:
            total = len(step.eligible_approver_ids)
            if step.state == 'waiting':
                needed = step._required_for(total)
            else:
                needed = step.required_approvals
            if step.approval_mode == 'any':
                label = _("Any 1 of %s", total)
            elif step.approval_mode == 'all':
                label = _("All %s", total)
            else:
                label = _("%(needed)s of %(total)s", needed=needed, total=total)
            if step.state in ('pending', 'approved') and step.approved_by_ids:
                label += _(" (%(done)s approved)", done=len(step.approved_by_ids))
            step.needs_label = label

    def _required_for(self, holders):
        """Approvals needed given ``holders`` eligible people (never more than there are)."""
        self.ensure_one()
        if self.approval_mode == 'all':
            return holders
        if self.approval_mode == 'count':
            return min(self.required_count, holders)
        return min(1, holders)

    def _activate(self):
        self.ensure_one()
        budget = self.approval_id.budget_id.sudo()
        approvers = self.env['budget.approval.rule.step']._approvers_for(
            self.job_ids, budget.company_id, exclude=self.approval_id.submitted_by)
        if not approvers:
            raise UserError(_(
                "Nobody can approve step \"%(step)s\": no employee of %(company)s other than the requester "
                "holds %(jobs)s.",
                step=self.name, company=budget.company_id.name, jobs=", ".join(self.job_ids.mapped('name'))))
        activities = self.env['mail.activity']
        for user in approvers:
            activities |= budget.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_("Approve budget"),
                note=_("Please review and approve or reject the budget %s.", budget.display_name),
                user_id=user.id,
                date_deadline=fields.Date.context_today(self))
        self.write({
            'state': 'pending',
            'approver_ids': [(6, 0, approvers.ids)],
            'required_approvals': self._required_for(len(approvers)),
            'approved_by_ids': [(5, 0, 0)],
            'activity_ids': [(6, 0, activities.ids)],
        })

    def _clear_activity(self, user=None):
        """Remove the approval To-Dos of the step, or only those of ``user`` when given."""
        activities = self.activity_ids
        if user:
            activities = activities.filtered(lambda a: a.user_id == user)
        activities.sudo().with_context(budget_approval_skip_intercept=True).unlink()

    def action_approve_selected(self):
        return self.budget_id._action_approval_decision('approve')

    def action_reject_selected(self):
        return self.budget_id._action_approval_decision('reject')

    def action_open_budget(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'budget.analytic',
            'res_id': self.budget_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
