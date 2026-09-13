# -*- coding: utf-8 -*-
{
    'name': 'CRM Kanban Total Count',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Show the stage total opportunity count next to the expected revenue in the CRM Kanban column header',
    'description': """
CRM Kanban Total Count
========================

Odoo's own CRM pipeline Kanban already shows, per stage column:

* the activity progress bar (green/yellow/red, ``activity_state``),
* a rotting-opportunity count badge (native ``mail`` "rotting mixin",
  already wired into ``crm``'s Kanban via ``is_rotting``),
* the stage's total expected revenue (the progress bar's
  ``sum_field="expected_revenue"`` aggregate).

The one thing missing natively is the stage's **total opportunity count**
printed next to that revenue figure. This module adds it, so the header
reads e.g.::

    [progress bar]   4            🎯18   $68,163
                      ^rotting      ^count ^revenue (native)

Implementation notes
---------------------
* This is a single QWeb template extension (``t-inherit-mode="extension"``)
  on ``crm.ColumnProgress`` — no JavaScript class, no new component, no
  Python model, no controller/route.
* The count is read directly from the Kanban group's own ``count``
  (``props.group.count``), which the Kanban view already loads from the
  server (``read_group``) for the currently active domain/filters
  (salesperson, team, search, folded state, ...) and keeps in sync on
  every drag/drop, create, archive and filter change through Odoo's
  normal reactive re-render — no extra RPC is issued by this module.
* The rotting count badge and the revenue aggregate (including its
  currency formatting) are entirely native and untouched.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['crm'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'crm_kanban_total_count/static/src/xml/crm_kanban_stage_header.xml',
            'crm_kanban_total_count/static/src/scss/crm_kanban_stage_header.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
