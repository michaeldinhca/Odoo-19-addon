# -*- coding: utf-8 -*-
{
    'name': 'NGYN Resource Planning',
    'version': '19.0.1.0.14',
    'category': 'Services/Project',
    'summary': 'Weekly resource planning workspace across projects, tasks and team capacity',
    'description': """
NGYN Resource Planning
=======================
A dense, multi-project weekly resourcing workspace built on top of Project and Timesheets.

Features (v1):
--------------
* Pin several projects at once and plan weekly hour allocations per task / team member,
  rounded to the nearest quarter hour.
* Live project health (On track / Stalled / Over burn), computed from time elapsed vs.
  hours logged against charged hours — no manual status setting required.
* A weekly team load strip showing, per person per week, hours allocated across *all*
  projects against a configurable 70% planning buffer (and a hard weekly capacity).
  Searchable by name, filterable by role, and pinnable to a short list.
* Past weeks lock automatically and show actual logged hours (from Timesheets) instead
  of the plan, so history can't be edited by accident.
* Adding a team member to a task uses a role-filtered picker instead of a long dropdown.

This module does not replace the Planning app — it is a lightweight, purpose-built
overview layer for staffing decisions across many projects at once.
""",
    'author': 'NGYN Solutions',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['project', 'hr', 'hr_timesheet', 'knowledge'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_views.xml',
        'views/resource_planning_menus.xml',
        'data/knowledge_articles.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ngyn_resource_planning/static/src/js/resource_planning_action.js',
            'ngyn_resource_planning/static/src/xml/resource_planning_templates.xml',
            'ngyn_resource_planning/static/src/scss/resource_planning.scss',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': '_backfill_ngyn_assignments',
}
