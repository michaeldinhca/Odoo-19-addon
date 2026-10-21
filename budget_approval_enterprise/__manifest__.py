{
    'name': 'Budget Approval (Enterprise)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Sequential approval workflow gating the Open action of Enterprise analytic budgets',
    'description': """
Budget Approval (Enterprise)
============================

Extends the Odoo Enterprise Budget Management app (``account_budget``) so a
draft budget must be approved before it can be opened.

Key features
------------
* Approval rules per company, matched on budget type and total budgeted amount.
* Each rule has ordered steps, each assigned to one or more job positions.
* Approvers act strictly in sequence, each step gets its own activity.
* Only an employee holding a position of the current step can approve or reject it
  (never the requester). The first holder to decide closes the step.
  Rejecting requires a reason and returns the budget to its requester.
* The budget is locked while waiting for approval. Changing the lines of an
  approved budget voids the approval.
* Open is blocked server-side until approved, not only hidden in the form.
* Full chatter trail and an Approvals tab on the budget form.
* Multi-company: rules, requests and access are company scoped.

This module depends on an Enterprise-licensed app and is therefore
distributed under the Odoo Enterprise Edition License.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'OEEL-1',
    'depends': ['account_budget', 'hr', 'mail'],
    'data': [
        'security/budget_approval_security.xml',
        'security/ir.model.access.csv',
        'views/budget_approval_rule_views.xml',
        'views/budget_approval_step_views.xml',
        'views/budget_analytic_views.xml',
        'wizard/budget_approval_decision_wizard_views.xml',
        'views/menus.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
