# Changelog

All notable changes to this module are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [19.0.2.0.0] - 2026-09-08

### Changed
- **Confirm/invoice workflow redesigned.** `action_confirm()` no longer
  creates an invoice — it only locks in the fee amount and sends a
  summary email (a running list of every confirmed-but-not-yet-invoiced
  fee for that customer), leaving a negotiation window for
  accounting/sales before any bill exists. A new bulk action, "Create
  Consolidated Invoice" (multi-select in the Late Fees list), lets an
  accountant combine any set of Confirmed fees for one customer — even
  across different original overdue invoices — into a single invoice
  with one line per fee, then sends one invoice email.
- `account.late.fee.state` gains `invoiced`; `waived` is now reachable
  from `confirmed` too (not just `draft`), since negotiation can still
  drop a locked-in fee before it's billed.
- `account.move.late_fee_status` values changed: `applied` → `confirmed`
  (locked in, not yet billed) and `invoiced` (billed) as two distinct
  states, replacing the old single `applied`.

### Removed
- **"Add Line to Same Invoice" application mode retired.** Every fee is
  now billed on a new, possibly-consolidated invoice; editing the
  original posted invoice in place is no longer supported.
  `late.fee.model.application_mode` and `account.late.fee.application_mode`
  removed.

### Added
- `account.late.fee.period_date` ("Fee Applies On") and per-cycle
  `overdue_days`, so each recurrence cycle states its own trigger date
  instead of reusing the generation date for every cycle.
- Per-model "Send Notification Email" toggle and two separate email
  template overrides (summary vs. invoice stage), each with an in-app
  "Edit Email Template" shortcut.

### Fixed
- Recurring models now backfill **every** elapsed-but-uncharged cycle in
  one cron run (capped at `max_occurrences`), not just the latest one —
  an invoice 3 monthly cycles overdue before the cron first catches it
  now correctly gets 3 separate fee lines instead of a single one.

## [19.0.1.0.0] - 2026-09-08

### Added
- Initial release: Late Fee Models (percentage/fixed, day/week/month,
  one-time or recurring with a cap), per-installment overdue detection
  respecting multi-installment payment terms, nightly cron generating
  draft fees, manual review/confirm workflow, same-invoice vs. new-invoice
  application (with automatic safe fallback when the original invoice was
  already sent or can't be reset to draft), self-explanatory fee
  descriptions reused across invoice lines and the customer email,
  partner/invoice exemptions, and company settings.
