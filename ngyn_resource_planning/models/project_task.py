# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    x_ngyn_assignment_ids = fields.One2many(
        'ngyn.task.assignment', 'task_id',
        string='Resource Assignments',
    )
