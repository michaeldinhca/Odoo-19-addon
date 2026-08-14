# -*- coding: utf-8 -*-
from odoo import api, models


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_ngyn_assignees()
        return lines

    def _sync_ngyn_assignees(self):
        """Anyone who's logged time against a task is clearly involved with
        it -- give them a real ngyn.task.assignment row too (at 0h, on top of
        whatever they've actually logged), even if nobody added them as an
        Assignee or through Resource Planning directly."""
        pairs = [
            (line.task_id.id, line.employee_id.id)
            for line in self if line.task_id and line.employee_id
        ]
        self.env['ngyn.task.assignment']._ensure_assignments(pairs)
