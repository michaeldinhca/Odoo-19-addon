from odoo import _, fields, models


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    provider_fee_enabled = fields.Boolean(
        string="Charge Payment Processing Fee",
        help="Automatically add a fee to the order/invoice total to cover this provider's "
             "processing cost, charged to the customer at checkout.",
    )
    provider_fee_fixed_amount = fields.Monetary(
        string="Fixed Fee", currency_field='main_currency_id',
        help="Flat amount added to the fee regardless of order size.",
    )
    provider_fee_percentage = fields.Float(
        string="Percentage Fee", digits=(16, 2),
        help="Percentage of the order/invoice amount (before the fee) added to the fee.",
    )
    provider_fee_amount_min = fields.Monetary(
        string="Minimum Fee", currency_field='main_currency_id',
        help="The computed fee is never charged below this amount. Leave at 0 for no floor.",
    )
    provider_fee_amount_max = fields.Monetary(
        string="Maximum Fee", currency_field='main_currency_id',
        help="The computed fee is never charged above this amount. Leave at 0 for no ceiling.",
    )
    provider_fee_order_threshold = fields.Monetary(
        string="Minimum Order Amount", currency_field='main_currency_id',
        help="The fee only applies to orders/invoices at or above this amount. Leave at 0 to "
             "always charge it.",
    )
    provider_fee_tax_mode = fields.Selection(
        [('none', "No Tax"),
         ('inherit', "Inherit From Order/Invoice"),
         ('manual', "Set Taxes Manually")],
        string="Fee Tax Mode", default='none', required=True,
        help="How to tax the fee line itself:\n"
             "- No Tax: the fee is charged tax-free.\n"
             "- Inherit From Order/Invoice: the fee gets the same taxes as the first regular "
             "line on the order/invoice being paid.\n"
             "- Set Taxes Manually: always use the taxes selected below.",
    )
    provider_fee_tax_ids = fields.Many2many(
        'account.tax', string="Fee Taxes",
        domain="[('company_id', 'parent_of', company_id), ('type_tax_use', '=', 'sale')]",
        help="Used only when the fee tax mode is 'Set Taxes Manually'.",
    )
    provider_fee_product_id = fields.Many2one(
        'product.product', string="Fee Product", copy=False, ondelete='set null', readonly=True,
        help="Service product used for the payment-processing-fee line. Created automatically "
             "the first time this provider actually charges a fee.",
    )

    def _compute_provider_fee(self, base_amount, target_currency=None):
        """Compute the fee this provider would charge on `base_amount` (in `target_currency`,
        defaulting to the provider's own currency). Returns 0.0 if the fee is disabled or the
        order doesn't meet the configured minimum order amount."""
        self.ensure_one()
        if not self.provider_fee_enabled or base_amount <= 0:
            return 0.0

        from_currency = self.main_currency_id
        to_currency = target_currency or from_currency
        company = self.company_id
        today = fields.Date.context_today(self)

        def convert(amount):
            if not amount or from_currency == to_currency:
                return amount
            return from_currency._convert(amount, to_currency, company, today)

        threshold = convert(self.provider_fee_order_threshold)
        if self.provider_fee_order_threshold and base_amount < threshold:
            return 0.0

        fee = convert(self.provider_fee_fixed_amount) + base_amount * (
            self.provider_fee_percentage / 100.0
        )
        fee_min = convert(self.provider_fee_amount_min)
        fee_max = convert(self.provider_fee_amount_max)
        if self.provider_fee_amount_min:
            fee = max(fee, fee_min)
        if self.provider_fee_amount_max:
            fee = min(fee, fee_max)

        return to_currency.round(max(fee, 0.0))

    def _get_or_create_fee_product(self):
        self.ensure_one()
        if self.provider_fee_product_id:
            return self.provider_fee_product_id
        product = self.env['product.product'].sudo().create({
            'name': _("%s Processing Fee", self.name),
            'type': 'service',
            'sale_ok': True,
            'purchase_ok': False,
            'invoice_policy': 'order',
            'list_price': 0.0,
            'company_id': self.company_id.id,
        })
        self.provider_fee_product_id = product
        return product

    def _get_fee_line_label(self):
        self.ensure_one()
        return _("[%(code)s_FEE] Payment Processing Fee", code=(self.code or 'PROVIDER').upper())

    def _resolve_fee_tax_ids(self, inherited_taxes=None):
        self.ensure_one()
        if self.provider_fee_tax_mode == 'manual':
            return self.provider_fee_tax_ids
        if self.provider_fee_tax_mode == 'inherit':
            return inherited_taxes if inherited_taxes is not None else self.env['account.tax']
        return self.env['account.tax']
