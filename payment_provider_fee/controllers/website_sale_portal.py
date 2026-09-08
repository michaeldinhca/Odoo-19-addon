from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.payment import PaymentPortal as WebsiteSalePaymentPortal

from .main import _format_provider_fees


class WebsiteSalePaymentProviderFee(WebsiteSale):
    """Preview-only: shows the fee each compatible provider would charge next to its option on
    the website checkout page. `website_sale` builds this page's values independently of
    `sale.controllers.portal.CustomerPortal._get_payment_values` (it calls that class's method
    directly rather than through `self`), so it needs its own override to get the same badges."""

    def _get_shop_payment_values(self, order, **kwargs):
        values = super()._get_shop_payment_values(order, **kwargs)
        providers_sudo = values.get('providers_sudo')
        if providers_sudo:
            values['provider_fees'] = _format_provider_fees(
                providers_sudo, order.amount_total, order.currency_id
            )
        return values


class WebsiteSalePaymentProviderFeePortal(WebsiteSalePaymentPortal):

    @route()
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        """Add/refresh the fee order line *before* the parent method compares the requested
        amount against `order.amount_total` and rejects a mismatch as a stale cart -- by the
        time that check runs, the order's own total must already include the fee."""
        provider_id = kwargs.get('provider_id')
        if provider_id:
            order_sudo = request.env['sale.order'].sudo().browse(order_id)
            if order_sudo.exists():
                provider_sudo = request.env['payment.provider'].sudo().browse(int(provider_id))
                requested_amount = (
                    float(kwargs['amount']) if kwargs.get('amount') else order_sudo.amount_total
                )
                kwargs['amount'] = order_sudo._resolve_payment_provider_fee(
                    provider_sudo, requested_amount
                )
        return super().shop_payment_transaction(order_id, access_token, **kwargs)
