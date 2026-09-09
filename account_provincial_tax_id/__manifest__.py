{
    'name': 'Provincial Tax ID',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Configurable secondary (e.g. provincial/regional) tax registration number per fiscal position',
    'description': """
Provincial Tax ID
==================

Adds a configurable secondary tax registration number (e.g. a Canadian
provincial tax ID) to Fiscal Positions, and prints it directly under the
company's GST/HST (or other) tax ID line on every standard document layout
(Quotations, Sales Orders, Invoices, Credit Notes, Purchase Orders, Delivery
Slips, and any other report using the standard external layout).

Key features
------------
* New "Provincial Tax ID" field on Fiscal Positions, independent of the
  native "Foreign Tax ID" (which only allows one value per country).
* Automatically resolved from the document's own fiscal position when set
  (Sales Orders, Invoices, Credit Notes, Purchase Orders, ...).
* Configurable per-company fallback (Delivery/Shipping vs Invoice/Billing
  address) used to resolve a fiscal position for documents that don't carry
  their own fiscal position (e.g. Delivery Slips).
* Works across all standard document layouts (Standard, Boxed, Bold,
  Striped, Folder, Wave, Bubble) via a single shared injection point -- no
  per-report template changes needed.
* Shows nothing when no Provincial Tax ID applies -- no empty lines.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/account_fiscal_position_views.xml',
        'views/res_config_settings_views.xml',
        'views/report_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
