# -*- coding: utf-8 -*-
{
    'name': 'Server Action Requests',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Tools',
    'summary': 'Expose a restricted "requests" HTTP client to Python server actions, automation rules and scheduled actions',
    'description': """
Server Action Requests
======================

Odoo Online (SaaS builds) makes ``requests`` available inside Python code of
server actions, so code such as ``requests.post(url, json=payload)`` works
there without any import. The stable build used on odoo.sh and on-premise
does not, so the same code fails with ``name 'requests' is not defined``
after a migration from Odoo Online.

This module adds ``requests`` back to the server action evaluation context,
wrapped with ``odoo.tools.safe_eval.wrap_module`` so only the HTTP helpers
and the exception classes are reachable (no sessions, adapters or internals).

* No views, no data, no new models.
* Uses ``setdefault``: if the Odoo build already provides ``requests``,
  this module changes nothing.
* Covers automation rules and scheduled actions too, since both run
  through ``ir.actions.server``.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
