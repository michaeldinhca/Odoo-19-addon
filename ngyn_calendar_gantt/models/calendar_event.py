# -*- coding: utf-8 -*-
from odoo import fields, models


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    x_ngyn_installer_ids = fields.Many2many(
        'res.partner',
        relation='ngyn_calendar_event_installer_rel',
        column1='event_id',
        column2='partner_id',
        string='Installers',
        help='Contacts responsible for carrying out this booking on site. '
             'Used to group the Calendar Timeline by installer.',
    )
