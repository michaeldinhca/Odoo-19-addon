# Changelog

All notable changes to this module are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [19.0.1.0.0] - 2026-09-08

### Added
- Initial release: per-provider payment processing fee (fixed + percentage,
  min/max caps, minimum order amount, optional tax on the fee itself).
- Fee applied as a dedicated order line before the payment transaction is
  created, for both website checkout and the "pay this quotation/order"
  customer portal page.
- Fee on an online-paid invoice: added directly to a draft invoice, or
  billed on a linked companion invoice (settled in the same payment)
  when the original invoice is already posted/sent.
- Fee only applies to full-amount payments; down payments and
  customer-chosen custom/partial amounts are left untouched.
- Server-side re-verification of the charged amount at transaction
  creation time, independent of whatever the browser sent.
- Fee preview badge next to each payment option, where this module
  overrides the relevant portal/checkout page.
