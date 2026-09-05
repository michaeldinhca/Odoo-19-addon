# -*- coding: utf-8 -*-
{
    'name': 'NGYN Calendar Timeline',
    'version': '19.0.1.1.0',
    'category': 'Productivity/Calendar',
    'summary': 'Read-only Gantt-style timeline for Calendar, grouped by CRM Opportunity or Installer',
    'description': """
NGYN Calendar Timeline
=======================
Odoo Community's Calendar has no Gantt/timeline view. When several bookings
land in the same time slot, the day/week calendar grid gets cramped, and
there's no way to see who (or which opportunity) is already busy.

This module adds a read-only weekly timeline under the Calendar app, built
from scratch as a plain OWL client action — it does not use, depend on, or
contain any code from Odoo Enterprise's Gantt view.

Features (v1):
--------------
* Rows grouped by either the CRM Opportunity (native
  `calendar.event.opportunity_id`) or by Installer (a new Contacts
  many2many field this module adds to the event) — pick which one in
  Calendar > Configuration > Settings.
* Overlapping bookings within the same row are stacked into separate lanes
  instead of visually overlapping, so a busy person or opportunity is easy
  to spot at a glance.
* Click a bar to open the underlying event.

v1 is intentionally read-only (no drag-to-reschedule yet).
""",
    'author': 'NGYN Solutions',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['calendar', 'crm'],
    'data': [
        'views/calendar_event_views.xml',
        'views/res_config_settings_views.xml',
        'views/calendar_gantt_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ngyn_calendar_gantt/static/src/js/calendar_gantt_action.js',
            'ngyn_calendar_gantt/static/src/xml/calendar_gantt_templates.xml',
            'ngyn_calendar_gantt/static/src/scss/calendar_gantt.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
