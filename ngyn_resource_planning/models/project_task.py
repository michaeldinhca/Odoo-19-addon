# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    x_ngyn_assignment_ids = fields.One2many(
        'ngyn.task.assignment', 'task_id',
        string='Resource Assignments',
    )

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks._sync_ngyn_assignees()
        return tasks

    def write(self, vals):
        res = super().write(vals)
        if 'user_ids' in vals:
            self._sync_ngyn_assignees()
        return res

    def _sync_ngyn_assignees(self):
        """Anyone in the native Assignees field (with a linked employee) gets
        a real ngyn.task.assignment row too, at 0h, so they show up in
        Resource Planning without needing to be added there separately."""
        pairs = [
            (task.id, user.employee_id.id)
            for task in self for user in task.user_ids if user.employee_id
        ]
        self.env['ngyn.task.assignment']._ensure_assignments(pairs)
