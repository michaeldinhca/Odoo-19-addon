from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BudgetApprovalRule(models.Model):
    _name = 'budget.approval.rule'
    _description = 'Budget Approval Rule'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    budget_type = fields.Selection(
        [('any', "Any"), ('revenue', "Revenue"), ('expense', "Expense"), ('both', "Both")],
        default='any', required=True)
    min_amount = fields.Monetary(
        string="Minimum Total Budgeted", currency_field='currency_id', default=0.0,
        help="The rule applies when the total budgeted amount of the budget is at or above this value.")
    step_ids = fields.One2many('budget.approval.rule.step', 'rule_id', string="Approval Steps", copy=True)

    def _matches(self, budget):
        self.ensure_one()
        if self.budget_type != 'any' and self.budget_type != budget.budget_type:
            return False
        return budget._approval_total_amount() >= self.min_amount

    @api.model
    def _get_matching_rule(self, budget):
        """First matching active rule (lowest sequence) of the budget's own company, else empty."""
        # sudo(): internal evaluation, must not depend on the current user's company switcher
        # or read access to the configuration, only on the budget's own company.
        rules = self.sudo().search([('company_id', '=', budget.company_id.id)])
        for rule in rules:
            if rule.step_ids and rule._matches(budget):
                return rule
        return self.browse()


class BudgetApprovalRuleStep(models.Model):
    _name = 'budget.approval.rule.step'
    _description = 'Budget Approval Rule Step'
    _order = 'sequence, id'

    rule_id = fields.Many2one('budget.approval.rule', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='rule_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Step Name")
    job_ids = fields.Many2many(
        'hr.job', 'budget_approval_rule_step_job_rel', 'step_id', 'job_id',
        string="Job Positions", required=True,
        help="Any employee of the budget's company holding one of these positions can approve this step.")

    approval_mode = fields.Selection(
        [('any', "Any one of them"), ('all', "All of them"), ('count', "At least N of them")],
        string="Approvals Needed", default='any', required=True,
        help="How many of the people holding these positions must approve before the step is done. "
             "A single rejection always rejects the step.")
    required_count = fields.Integer(
        string="N", default=2, help="Number of approvals needed when 'At least N' is selected.")

    @api.constrains('approval_mode', 'required_count')
    def _check_required_count(self):
        for step in self:
            if step.approval_mode == 'count' and step.required_count < 1:
                raise ValidationError(_("The number of approvals needed must be at least 1."))

    @api.constrains('job_ids', 'rule_id')
    def _check_jobs(self):
        for step in self:
            if not step.job_ids:
                raise ValidationError(_("Each step needs at least one job position."))
            company = step.rule_id.company_id
            foreign = step.job_ids.filtered(lambda j: j.company_id and j.company_id != company)
            if foreign:
                raise ValidationError(_(
                    "Job position(s) %(jobs)s belong to another company than the rule's company %(company)s.",
                    jobs=", ".join(foreign.mapped('name')), company=company.name))

    @api.model
    def _approvers_for(self, jobs, company, exclude=None):
        """Internal users of ``company`` whose employee holds one of ``jobs``.

        ``exclude`` (the requester) can never approve their own budget.
        """
        # sudo(): resolving who holds a position must not depend on the caller's HR access.
        employees = self.env['hr.employee'].sudo().search([
            ('company_id', '=', company.id),
            ('job_id', 'in', jobs.ids),
            ('user_id', '!=', False),
        ])
        users = employees.user_id.filtered(lambda u: u.active and not u.share and company in u.company_ids)
        return users - exclude if exclude else users
