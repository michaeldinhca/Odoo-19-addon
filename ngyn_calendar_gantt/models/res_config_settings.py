# -*- coding: utf-8 -*-
from odoo import fields, models

# Which calendar.event field the Timeline groups rows by. A plain list, not a
# generic field introspection, so adding a third option later is a one-line
# change here (and its matching label in calendar_gantt_action.js) rather
# than a redesign.
GANTT_GROUPBY_FIELDS = [
    ('opportunity_id', 'Opportunity (CRM)'),
    ('x_ngyn_installer_ids', 'Installer'),
]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    x_ngyn_gantt_groupby_field = fields.Selection(
        GANTT_GROUPBY_FIELDS,
        string='Timeline Group By',
        config_parameter='ngyn_calendar_gantt.groupby_field',
        default='opportunity_id',
        help='Which field the Calendar Timeline (Gantt-style view) uses to group events into rows.',
    )
