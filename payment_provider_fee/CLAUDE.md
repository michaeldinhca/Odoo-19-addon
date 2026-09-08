# payment_provider_fee — Notes for AI coding assistants

Odoo 19. Depends on `payment`, `sale`, `account_payment`, `website_sale` --
all Community/LGPL-3, confirmed by reading each module's own
`__manifest__.py` `license` field before using it as a reference (see
`odoo_no_enterprise_code` standing rule: never use Enterprise source, even
bundled in the same download, without checking the license field first).

## What this module actually charges, and where

Three independent payment entry points exist in stock Odoo, and each
builds its own rendering context and calls transaction creation
differently. This module has to hook all three separately:

1. **Website checkout** (`/shop/payment/transaction/<order_id>`,
   `website_sale.controllers.payment.PaymentPortal.shop_payment_transaction`).
   This route compares the client-sent `amount` against
   `order.amount_total` *before* creating the transaction and rejects a
   mismatch as "the cart has been updated". So the fee order line must be
   added, and `kwargs['amount']` overwritten, **before** calling `super()`
   -- see `controllers/website_sale_portal.py`.
2. **Portal "pay this quotation/order"**
   (`/my/orders/<id>/transaction`,
   `sale.controllers.portal.PaymentPortal.portal_order_transaction`). No
   such pre-check exists here; the fee is applied inside the shared
   `_create_transaction` override instead (see below).
3. **Portal "pay this invoice"** (`/invoice/transaction/<id>`,
   `account_payment.controllers.payment.PaymentPortal.invoice_transaction`
   -> `_process_transaction` -> `_create_transaction`). Also no pre-check;
   handled the same way as (2).

All three ultimately call `self._create_transaction(...)` via normal
Python MRO, so `controllers/main.py`'s `PaymentProviderFeePortal`
(subclassing `payment.controllers.portal.PaymentPortal`) is the single
authoritative place the actual charged `amount` is (re)computed --
whatever the browser sent is never trusted on its own. Calling the
sale-order fee resolution twice per request (once in the website
override, once again here) is intentional and safe: `_resolve_payment_provider_fee`
is idempotent (see below).

**Gotcha that cost real investigation time**: `website_sale`'s
`_get_shop_payment_values` calls
`sale_portal.CustomerPortal._get_payment_values(self, order, ...)` --
note that's the class object's method looked up directly, not
`self._get_payment_values(...)`. Because of that, overriding
`_get_payment_values` on a `sale.controllers.portal.CustomerPortal`
subclass (`controllers/sale_portal.py`) does **not** affect the website
checkout page at all -- normal controller-merge MRO is bypassed by this
literal unbound-method call. That's why the fee-preview badge injection
needs its own separate override in `controllers/website_sale_portal.py`
(`WebsiteSale._get_shop_payment_values`) rather than being inherited for
free from the sale-portal override.

## Full-payment vs. down-payment / custom-amount detection

There is no explicit flag telling a controller "this is a down payment"
by the time `_create_transaction` runs. The fee must **not** apply to a
down payment or a customer-chosen custom/partial amount -- only to a
payment of the full amount due. Detection is by comparison, not a flag:

- `sale.order._resolve_payment_provider_fee(provider, requested_amount)`:
  if `requested_amount` equals the order's current pre-fee total, treat
  it as a full payment and apply the fee. If it instead already equals
  the *post*-fee total and a fee line already exists, it's the second of
  the two same-request calls described above -- no-op, already correct.
  Otherwise it's a down payment/partial amount: strip any stale fee line
  and leave the amount untouched.
- `account.move._resolve_payment_provider_fee(provider, requested_amount)`:
  same idea, comparing against `_get_invoice_next_payment_values()['next_amount_to_pay']`
  (freshly recomputed from the invoice itself, never from client input).

Do not "simplify" either of these into always forcing
`amount = order.amount_total` -- that silently breaks legitimate down
payments on confirmed sale orders (portal pay-now supports paying a
`prepayment_percent`-based down payment, a real, separate amount from
`amount_total`).

## Posted/sent invoices are never mutated

Same safety precedent already established by `account_late_fee`
(`[[odoo_late_fee_module]]`): once an invoice is posted (and especially
once sent), this module never appends a line to it or reopens it to
draft. For a draft invoice, the fee is added as a normal line. For a
posted invoice, `_get_or_create_payment_provider_fee_invoice` creates
(or reuses) a small linked companion `account.move`
(`payment_provider_fee_origin_invoice_id` back-reference,
`is_payment_provider_fee_invoice = True`), posts it immediately, and
both invoice ids are folded into the transaction's `invoice_ids` so
Odoo's own multi-invoice payment reconciliation settles both from one
customer payment. No custom reconciliation code was written for this --
it's entirely stock Odoo behavior, just given two invoice ids instead of
one.

## Known scope limits (deliberate, not bugs)

- Only a **single** sale order or **single** invoice per transaction is
  fee-eligible. The "pay all overdue invoices at once"
  (`/invoice/transaction/overdue`) batch flow is left alone -- which
  invoice a fee would even belong to is ambiguous there.
- No live AJAX round-trip for the fee preview badge. All compatible
  providers' fees are computed once, server-side, at page-render time
  and passed into the QWeb context as `provider_fees` (a plain
  `{provider_id: "+ formatted amount"}` dict); `views/payment_templates.xml`
  inherits `payment.method_form` to render it next to the payment option
  label. The visible order/invoice **total** does not live-update when
  the customer switches provider -- the badge is informational only.
  A v2 could patch `@payment/interactions/payment_form` to do that; it
  was deliberately left out to avoid touching Odoo's frontend JS
  internals without the ability to test them live in this session.
- Provider fee fields are stored in the payment provider's
  `main_currency_id` (its company's currency) and converted via
  `res.currency._convert` to the order/invoice currency when they
  differ, mirroring how `payment.provider.maximum_amount` already works.

## Fee tax modes

`provider_fee_tax_mode` on `payment.provider`:
- `none` (default): fee line is untaxed.
- `manual`: always uses `provider_fee_tax_ids`.
- `inherit`: uses the tax(es) on the order/invoice's first regular
  (non-display-type, non-fee) line as a stand-in for "the same tax as
  everything else on this document". This is a heuristic, not a true
  per-line tax mirror -- documents with mixed tax rates across lines
  will only inherit the first line's rate onto the fee.

## Versioning

Bump `version` in `__manifest__.py` (`19.0.{major}.{minor}.{patch}`) and
add an entry to `CHANGELOG.md` for any behavior change.
