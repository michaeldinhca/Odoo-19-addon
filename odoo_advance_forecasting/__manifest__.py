{
    'name': 'Advanced Cash Flow Forecasting',
    'version': '19.0.1.10.0',
    'category': 'Accounting/Accounting',
    'summary': 'Forecast future cash position from confirmed invoices, bills, sale and purchase orders',
    'description': """
Advanced Cash Flow Forecasting
===============================

Two forecasting methods on the same Forecast Scenario record:

**Confirmed Documents** - a deterministic snapshot built only from confirmed
financial documents:

* Posted, unpaid customer invoices (incoming)
* Posted, unpaid vendor bills (outgoing)
* Confirmed sale orders, for whatever amount is not yet posted-invoiced
  (incoming) - correctly handles down payments and partial invoicing
* Confirmed purchase orders, for whatever amount is not yet posted-billed
  (outgoing) - same for down payments/partial billing

**Historical Trend (Predictive)** - extrapolates from realized bank/cash
activity: a trailing weekly average of actual incoming/outgoing cash over a
configurable lookback period, projected flat forward with a min/max range,
to cover the part of the horizon that isn't backed by any confirmed
document yet. Deliberately not seasonal/ML-based in v1 - that needs more
history than a brand-new install of this module has.

Known limitations (v1):

* Sale/purchase orders are only included when their currency matches the
  company currency. Foreign-currency orders are excluded from the forecast
  until a currency-conversion phase is added.
* Credit notes/refunds against an order are not netted into the
  "already invoiced" calculation - only regular invoices/bills are counted.
  An order with a refund could show a "remaining to invoice" amount that's
  slightly off; not expected to be common, revisit if it comes up.
* Historical Trend does not distinguish a one-off large entry (e.g. an
  opening bank-statement synchronization balance) from real recurring
  activity - it could skew whichever week's average it falls into.
""",
    'author': 'NGYN Solution Inc.',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['account', 'sale', 'purchase', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/cash_flow_forecast_security.xml',
        'views/res_config_settings_views.xml',
        'report/cash_flow_forecast_report_views.xml',
        'views/cash_flow_forecast_scenario_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
