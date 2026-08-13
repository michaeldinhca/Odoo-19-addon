# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    x_ngyn_weekly_target_hours = fields.Float(
        string='Weekly Planning Buffer (h)',
        default=28.0,
        help='Target hours per week for planning purposes — usually well under a full '
             'week (e.g. 70% of 40h) to leave room for admin, write-off, and unplanned work. '
             'The weekly load view turns amber once a person is scheduled past this.',
    )
    x_ngyn_weekly_hard_hours = fields.Float(
        string='Weekly Hard Capacity (h)',
        default=40.0,
        help='This person\'s full weekly capacity. The weekly load view turns red once '
             'a person is scheduled past this.',
    )
