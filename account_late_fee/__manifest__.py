{
    'name': 'Late Fee Management',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Configurable late payment fees for customer invoices',
    'description': """
Late Fee Management
====================

Automate late-payment fees on customer invoices, correctly respecting Odoo
payment terms, including multi-installment terms.

Key features
------------
* Configurable Late Fee Models: percentage or fixed amount, charged per
  day/week/month, one-time or recurring with a cap, one marked as the
  company default.
* Per-installment overdue detection: a multi-installment invoice is only
  charged on the installment(s) that are actually overdue, never on
  installments not yet due.
* Nightly automatic computation, with mandatory accountant review/confirm
  before anything is posted or emailed to the customer.
* Fully self-explanatory fee descriptions on the invoice line and in the
  customer notification email: original invoice, installment, overdue
  amount, days overdue, calculation shown transparently, new total due.
* Per-model choice of applying the fee to the same invoice or issuing a
  new, linked late-fee invoice, with an automatic safe fallback to a new
  invoice when the original was already sent to the customer or can no
  longer be reset to draft.
* Partner- and invoice-level exemptions.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/account_late_fee_security.xml',
        'views/late_fee_model_views.xml',
        'views/account_late_fee_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/account_late_fee_menus.xml',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
