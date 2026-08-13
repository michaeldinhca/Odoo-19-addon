# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    x_ngyn_charged_hours = fields.Float(
        string='Charged Hours',
        help='Hours sold / charged to the client for this task. '
             'This is the budget the Resource Planning workspace plans against.',
    )
    x_ngyn_assignment_ids = fields.One2many(
        'ngyn.task.assignment', 'task_id',
        string='Resource Assignments',
    )
