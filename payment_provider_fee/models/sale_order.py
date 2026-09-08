from odoo import Command, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_payment_provider_fee_lines(self):
        return self.order_line.filtered('is_payment_provider_fee')

    def _get_amount_total_excluding_payment_provider_fee(self):
        self.ensure_one()
        fee_lines = self._get_payment_provider_fee_lines()
        return self.amount_total - sum(fee_lines.mapped('price_total'))

    def _apply_payment_provider_fee(self, provider):
        """Replace the dedicated payment-provider-fee line with one for `provider`, or strip it
        entirely if `provider` is falsy or charges no fee on this order. Returns the resulting
        `amount_total` (fee-inclusive when a fee was applied).
        """
        self.ensure_one()
        base_amount = self._get_amount_total_excluding_payment_provider_fee()
        self._get_payment_provider_fee_lines().unlink()

        if provider and self.state in ('draft', 'sent', 'sale'):
            fee_amount = provider._compute_provider_fee(base_amount, self.currency_id)
            if fee_amount:
                regular_lines = self.order_line.filtered(lambda l: not l.display_type)
                fee_taxes = provider._resolve_fee_tax_ids(regular_lines[:1].tax_ids)
                self.order_line = [Command.create({
                    'product_id': provider._get_or_create_fee_product().id,
                    'name': provider._get_fee_line_label(),
                    'product_uom_qty': 1,
                    'price_unit': fee_amount,
                    'tax_ids': [Command.set(fee_taxes.ids)],
                    'is_payment_provider_fee': True,
                })]
        return self.amount_total

    def _resolve_payment_provider_fee(self, provider, requested_amount):
        """Idempotently resolve the amount to actually charge for `provider`.

        The fee is only applied when `requested_amount` matches the order's current pre-fee
        total, i.e. the customer is paying the full order -- down payments and other partial
        amounts are left untouched. Safe to call more than once for the same request (e.g. once
        to update the cart before the website's own amount check, and again when the payment
        transaction is actually created).
        """
        self.ensure_one()
        currency = self.currency_id
        pre_fee_total = self._get_amount_total_excluding_payment_provider_fee()

        if currency.compare_amounts(requested_amount, pre_fee_total) == 0:
            return self._apply_payment_provider_fee(provider)

        if (
            provider
            and self._get_payment_provider_fee_lines()
            and currency.compare_amounts(requested_amount, self.amount_total) == 0
        ):
            # Already fee-inclusive from an earlier call in the same request.
            return self.amount_total

        # Not a full-order payment (down payment / custom partial amount): don't charge a fee,
        # and drop any stale fee line left over from a previous provider selection.
        self._apply_payment_provider_fee(False)
        return requested_amount


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_payment_provider_fee = fields.Boolean(
        string="Is Payment Processing Fee", copy=False, default=False,
    )
