{
    'name': 'Payment Provider Fee',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment',
    'summary': 'Automatically charge back Stripe/PayPal processing fees on online payments',
    'description': """
Payment Provider Fee
=====================

Automatically charge customers a configurable surcharge to cover the
transaction fee of the payment provider (Stripe, PayPal, or any other
provider) they choose at checkout, on both the website store and the
customer portal (quotations, sales orders, and invoices paid online).

Key features
------------
* Per-provider fee configuration: fixed amount, percentage of the order,
  minimum/maximum fee caps, and a minimum order amount before the fee
  applies.
* Optional tax handling on the fee itself: no tax, inherit the taxes
  used on the rest of the order/invoice, or a manually chosen tax.
* The fee is added as a clearly labelled service line on the sales
  order before the payment transaction is created, so it flows through
  to the invoice like any other line.
* For an already posted/sent invoice paid through the customer portal,
  the fee is billed on a small linked companion invoice instead of
  editing the original document, and both are settled together by the
  same payment.
* Fee is only charged when the customer is paying the full amount due;
  down payments and custom partial amounts are left untouched.
* All fee computation is re-verified server-side when the payment
  transaction is created, so the amount charged cannot be manipulated
  from the browser.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['payment', 'sale', 'account_payment', 'website_sale'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
