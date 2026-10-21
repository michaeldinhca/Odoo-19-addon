from odoo import api, models


class BudgetLine(models.Model):
    """Guard the approved content of a budget: its budgeted amounts.

    Only changes that move money are guarded. Automations (for example one that adds a
    zero-amount line when a purchase order line mentions a new division) must keep working
    while the budget waits for approval, because a zero-amount line changes nothing that
    the approvers are looking at.
    """
    _inherit = 'budget.line'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('budget_approval_bypass'):
            budget_ids = [v['budget_analytic_id'] for v in vals_list
                          if v.get('budget_analytic_id') and v.get('budget_amount')]
            self.env['budget.analytic'].browse(budget_ids)._approval_on_content_change()
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('budget_approval_bypass'):
            changes_amount = 'budget_amount' in vals and any(
                abs(line.budget_amount - (vals['budget_amount'] or 0.0)) > 0.005 for line in self)
            moves_money = changes_amount or 'budget_analytic_id' in vals
            # moving a line that carries an amount to another account changes what is approved too
            # (the budget-level check also freezes amounts once approved, see budget.analytic)
            moves_amount = 'account_id' in vals and bool(self.filtered('budget_amount'))
            if moves_money or moves_amount:
                budgets = self.budget_analytic_id
                if vals.get('budget_analytic_id'):
                    budgets |= self.env['budget.analytic'].browse(vals['budget_analytic_id'])
                budgets._approval_on_content_change()
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('budget_approval_bypass'):
            self.filtered('budget_amount').budget_analytic_id._approval_on_content_change()
        return super().unlink()
