from odoo.fields import Command
from odoo.http import request

from odoo.addons.payment.controllers import portal as payment_portal


def _format_provider_fees(providers_sudo, base_amount, currency):
    """Preview-only helper: pre-format, per compatible provider, the fee that would be charged
    on `base_amount`, for display next to the provider's option. Skips providers with no fee."""
    fees = {}
    for provider_sudo in providers_sudo:
        fee_amount = provider_sudo._compute_provider_fee(base_amount, currency)
        if fee_amount:
            fees[provider_sudo.id] = "+ %s" % currency.format(fee_amount)
    return fees


def _relation_command_ids(commands):
    """Best-effort extraction of the ids a list of `Command` tuples would end up setting on a
    Many2many/One2many field, e.g. `[Command.set([1, 2])]` -> `[1, 2]`."""
    ids = []
    for command in commands or []:
        if command[0] == Command.SET:
            ids = list(command[2])
        elif command[0] == Command.LINK:
            ids.append(command[1])
    return ids


class PaymentProviderFeePortal(payment_portal.PaymentPortal):
    """Central, tamper-proof enforcement point for the payment-provider fee: whatever amount the
    client requested, the amount actually charged for a sale order or invoice payment is always
    re-derived here from the source document, never trusted verbatim from the browser."""

    def _create_transaction(
        self, provider_id, amount, currency_id, custom_create_values=None, **kwargs
    ):
        custom_create_values = dict(custom_create_values or {})
        provider = (
            request.env['payment.provider'].sudo().browse(provider_id) if provider_id else None
        )
        if provider:
            sale_order_ids = _relation_command_ids(custom_create_values.get('sale_order_ids'))
            invoice_ids = _relation_command_ids(custom_create_values.get('invoice_ids'))
            if len(sale_order_ids) == 1:
                order_sudo = request.env['sale.order'].sudo().browse(sale_order_ids[0])
                amount = order_sudo._resolve_payment_provider_fee(provider, amount)
            elif len(invoice_ids) == 1:
                invoice_sudo = request.env['account.move'].sudo().browse(invoice_ids[0])
                amount, linked_ids = invoice_sudo._resolve_payment_provider_fee(provider, amount)
                if len(linked_ids) > 1:
                    custom_create_values['invoice_ids'] = [Command.set(linked_ids)]

        return super()._create_transaction(
            provider_id=provider_id,
            amount=amount,
            currency_id=currency_id,
            custom_create_values=custom_create_values,
            **kwargs,
        )

    def _get_extra_payment_form_values(self, **kwargs):
        form_values = super()._get_extra_payment_form_values(**kwargs)
        providers_sudo = kwargs.get('providers_sudo')
        amount = kwargs.get('amount')
        currency = kwargs.get('currency')
        if providers_sudo and amount and currency:
            form_values['provider_fees'] = _format_provider_fees(providers_sudo, amount, currency)
        return form_values
