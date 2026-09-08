from odoo import Command, _, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_payment_provider_fee_invoice = fields.Boolean(
        string="Is Payment Processing Fee Invoice", copy=False, default=False,
    )
    payment_provider_fee_origin_invoice_id = fields.Many2one(
        'account.move', string="Fee For Invoice", copy=False, index=True,
        help="The invoice this payment-processing-fee invoice was generated for.",
    )
    payment_provider_fee_provider_id = fields.Many2one(
        'payment.provider', string="Fee Provider", copy=False,
        help="The payment provider whose fee this companion invoice bills.",
    )

    def _get_payment_provider_fee_lines(self):
        return self.invoice_line_ids.filtered('is_payment_provider_fee')

    def _resolve_payment_provider_fee(self, provider, requested_amount):
        """Resolve the amount to actually charge for `provider` when paying this single
        (posted or draft) customer invoice, and the list of invoice ids the payment transaction
        should be linked to.

        The fee is only applied when `requested_amount` matches the invoice's standard next
        payment amount -- a customer-chosen custom/partial amount is left untouched. A draft
        invoice gets the fee added as a normal line; a posted/sent invoice is never mutated --
        instead a small linked companion invoice for just the fee is created (or reused) and
        folded into the same payment so standard multi-invoice reconciliation settles both.

        :return: tuple (amount_to_charge, invoice_ids_to_link)
        """
        self.ensure_one()
        currency = self.currency_id
        base_amount = self._get_invoice_next_payment_values()['next_amount_to_pay']

        if currency.compare_amounts(requested_amount, base_amount) != 0:
            return requested_amount, [self.id]

        fee_amount = provider._compute_provider_fee(base_amount, currency) if provider else 0.0
        if not fee_amount:
            return base_amount, [self.id]

        if self.state == 'draft':
            self._get_payment_provider_fee_lines().unlink()
            regular_lines = self.invoice_line_ids.filtered(lambda l: not l.display_type)
            fee_taxes = provider._resolve_fee_tax_ids(regular_lines[:1].tax_ids)
            self.invoice_line_ids = [Command.create({
                'product_id': provider._get_or_create_fee_product().id,
                'name': provider._get_fee_line_label(),
                'quantity': 1,
                'price_unit': fee_amount,
                'tax_ids': [Command.set(fee_taxes.ids)],
                'is_payment_provider_fee': True,
            })]
            return self.amount_total, [self.id]

        fee_invoice = self._get_or_create_payment_provider_fee_invoice(provider, fee_amount)
        return base_amount + fee_amount, [self.id, fee_invoice.id]

    def _get_or_create_payment_provider_fee_invoice(self, provider, fee_amount):
        self.ensure_one()
        existing = self.env['account.move'].sudo().search([
            ('payment_provider_fee_origin_invoice_id', '=', self.id),
            ('payment_provider_fee_provider_id', '=', provider.id),
            ('state', '!=', 'cancel'),
            ('payment_state', 'not in', ('paid', 'in_payment', 'reversed')),
        ], limit=1)
        if existing:
            if existing.state == 'draft':
                existing._get_payment_provider_fee_lines().write({'price_unit': fee_amount})
                return existing
            if existing.currency_id.compare_amounts(existing.amount_total, fee_amount) == 0:
                return existing
            # A posted companion invoice exists but for a different amount than the fee is
            # currently configured for: leave it untouched and create a fresh one below rather
            # than editing a document that may already have been sent to the customer.

        regular_lines = self.invoice_line_ids.filtered(lambda l: not l.display_type)
        fee_taxes = provider._resolve_fee_tax_ids(regular_lines[:1].tax_ids)
        fee_invoice = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_origin': self.name,
            'ref': _("Payment Processing Fee - %s", self.name),
            'journal_id': self.journal_id.id,
            'is_payment_provider_fee_invoice': True,
            'payment_provider_fee_origin_invoice_id': self.id,
            'payment_provider_fee_provider_id': provider.id,
            'invoice_line_ids': [Command.create({
                'product_id': provider._get_or_create_fee_product().id,
                'name': provider._get_fee_line_label(),
                'quantity': 1,
                'price_unit': fee_amount,
                'tax_ids': [Command.set(fee_taxes.ids)],
                'is_payment_provider_fee': True,
            })],
        })
        fee_invoice.action_post()
        return fee_invoice


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    is_payment_provider_fee = fields.Boolean(
        string="Is Payment Processing Fee", copy=False, default=False,
    )
