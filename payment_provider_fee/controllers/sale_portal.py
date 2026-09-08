from odoo.addons.sale.controllers.portal import CustomerPortal as SaleCustomerPortal

from .main import _format_provider_fees


class SalePaymentProviderFeePortal(SaleCustomerPortal):
    """Preview-only: shows the fee each compatible provider would charge next to its option on
    the "pay this quotation/order" portal page. The actual charge is enforced separately, in
    `PaymentProviderFeePortal._create_transaction`."""

    def _get_payment_values(self, order_sudo, is_down_payment=False, payment_amount=None, **kwargs):
        values = super()._get_payment_values(
            order_sudo, is_down_payment=is_down_payment, payment_amount=payment_amount, **kwargs
        )
        providers_sudo = values.get('providers_sudo')
        if providers_sudo and not is_down_payment:
            values['provider_fees'] = _format_provider_fees(
                providers_sudo, values['amount'], order_sudo.currency_id
            )
        return values
