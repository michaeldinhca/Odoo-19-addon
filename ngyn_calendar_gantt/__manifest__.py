# -*- coding: utf-8 -*-
{
    'name': 'NGYN Calendar Timeline',
    'version': '19.0.1.2.1',
    'category': 'Productivity/Calendar',
    'summary': 'Read-only Gantt-style timeline for Calendar, grouped by CRM Opportunity or Attendee',
    'description': """
NGYN Calendar Timeline
=======================
Odoo Community's Calendar has no Gantt/timeline view. When several bookings
land in the same time slot, the day/week calendar grid gets cramped, and
there's no way to see who (or which opportunity) is already busy.

This module adds a weekly timeline under the Calendar app, built from scratch
as a plain OWL client action — it does not use, depend on, or contain any code
from Odoo Enterprise's Gantt view.

Features:
---------
* A real Odoo search bar (Filters / Group By / Favorites) — Group By
  Opportunity or Attendee out of the box; add more via the module's own
  `<search>` view, no code change needed.
* Overlapping bookings within the same row are stacked into separate lanes
  instead of visually overlapping, so a busy person or opportunity is easy
  to spot at a glance.
* Click a bar to open the event in a popup editor; drag its left/right edge
  to reschedule its start/end time directly on the timeline.
* A quick-view icon on each row (when grouped by Opportunity) opens that
  CRM record in a lightweight popup, no chatter panel.
* A New button creates a fresh event from the timeline.
""",
    'author': 'NGYN Solutions',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['calendar', 'crm'],
    'data': [
        'views/calendar_event_search_views.xml',
        'views/crm_lead_view_form_popup.xml',
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
