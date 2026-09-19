{
    'name': 'Enterprise Remittance Management',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Vendor payment allocation snapshots, remittance slips (PDF), remittance emails and controlled payment cancellation',
    'description': """
Enterprise Remittance Management
================================

Records exactly which vendor bills and credits every payment settled, keeps
that history immutable, and builds the vendor-facing documents from it.

Key features
------------
* Allocation snapshot captured inside the native "Register Payment" flow,
  BEFORE reconciliation, using the wizard's own payment-to-source-lines
  mapping (no vendor matching, no reliance on reconciled_bill_ids).
* Relational, immutable allocation lines per payment: original amount,
  amount due before payment, applied amount (payment and credit offset
  shown separately), remaining immediately after payment, document type,
  currency.
* Ownership trail of every reconciliation created by the registration, so a
  bill/credit offset can be told apart from pre-existing reconciliations.
* Controlled reset / cancel / delete of a payment: keep the bill-credit
  offsets (safe default) or reverse only the offsets that are provably owned
  by that registration and still safe to reverse.
* Native QWeb PDF "Remittance Slip" bound to payments, with a clearly
  labelled fallback for legacy payments that have no snapshot.
* Vendor remittance email with the PDF slip attached.
* Optional, read-mostly migration utility for legacy Studio allocation data.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['account', 'mail'],
    'data': [
        'security/remittance_security.xml',
        'security/ir.model.access.csv',
        'views/remittance_registration_views.xml',
        'wizard/remittance_cancel_wizard_views.xml',
        'wizard/remittance_migration_wizard_views.xml',
        'views/account_payment_views.xml',
        'views/res_config_settings_views.xml',
        'report/remittance_slip_report.xml',
        'report/remittance_slip_templates.xml',
        'data/mail_template_data.xml',
        'views/menus.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
