# account_late_fee — Notes for AI coding assistants

Odoo 19, Community-compatible (`depends: ['account', 'mail']` only — never
add an Enterprise-only dependency to this module).

## Core design invariant

Overdue detection is **per installment**, never per invoice. It reads
`account.move.line` records where `display_type == 'payment_term'` and
`account_type == 'asset_receivable'`, each with its own `date_maturity`
and residual amount. Never key logic off `account.move.invoice_date_due`
or the invoice's overall balance — a multi-installment invoice must only
be charged on the installment(s) actually overdue.

## Key models

- `late.fee.model` — configuration (percentage/fixed, day/week/month,
  one-time/recurring with cap, product/journal, two email template
  overrides). No longer has an "apply to same invoice" option — retired
  2026-09-08, see Workflow below.
- `account.late.fee` — one row per charged/pending `(invoice_line_id,
  period_index)` pair. That pair is the idempotency key, enforced by a
  DB unique constraint — the nightly cron must be safe to re-run.
- `description` on `account.late.fee` is the single source of truth for
  the human-readable explanation (invoice line label, new invoice line,
  and email body all read this same field — never regenerate the text
  in more than one place).
- For a `recurring` model, `_generate_for_line` must backfill **every**
  uncharged elapsed cycle (1..current, capped at `max_occurrences`) as
  separate records in one run, never just the latest cycle — an invoice
  that goes unnoticed for 3 monthly cycles before the cron first catches
  it must get 3 separate fee lines, not one. Each record's `period_date`
  and `overdue_days` describe *that cycle's* trigger date, not "today"
  reused across cycles. This was a real bug found in production
  (`ineng_pilot_15Aug`, 2026-09-08) — regression-tested by
  `test_recurring_backfills_all_elapsed_periods_on_first_run`.

## Workflow (redesigned 2026-09-08 — three stages, not two)

1. **Cron** (`_cron_generate_late_fees`, daily) creates `draft` ("To
   Review") records only. No email, no invoice.
2. **`action_confirm()`** locks in the amount (state → `confirmed`) and
   sends a **summary email** — a running list of every
   confirmed-but-not-yet-invoiced fee for that customer, generated fresh
   each time from *all* their outstanding confirmed fees, not just the
   one(s) just confirmed. **Still no invoice exists at this point.** This
   is deliberately a negotiation window: accounting/sales talk to the
   customer and can still `action_waive()` a confirmed fee if the number
   changes. Confirming several fees in one call sends **one** email per
   affected customer, never one per fee — avoid ever reintroducing
   per-fee email sends here, that was the exact spam problem this
   redesign fixes.
3. **`action_create_consolidated_invoice()`** is a bulk action (bound via
   `ir.actions.server` + `binding_model_id`/`binding_view_types`, so it
   appears in the list view's selection toolbar) that a human triggers
   manually after negotiation settles: select any set of `confirmed` fees
   for **one customer** (they can span multiple original overdue
   invoices — only same-partner/same-company is enforced) and it creates
   **one** invoice with one line per fee, posts it, sets state →
   `invoiced`, and sends **one** invoice email listing every line.

There is no more automatic/immediate invoicing on confirm, and no more
"add a line to the original invoice" option — both were retired in favor
of this deferred, always-new-and-possibly-multi-source consolidated
invoice. `late.fee.model.application_mode` and the `_apply_same_invoice`/
`_apply_new_invoice` methods are gone; don't resurrect them without
re-confirming the flow with the user first, since this was an explicit,
deliberate product decision, not a bug fix.

Both email methods (`_send_confirmation_summary_email`,
`_send_invoice_notification_email`) build their itemized HTML in Python
(`_build_fee_list_html`, reused by both) and inject it via
`template.send_mail(..., email_values={'body_html': ...})` rather than
relying on the stored `mail.template.body_html` directly — this is
because each email covers a *variable-length list* of `account.late.fee`
records, not a single one, so the QWeb `object.xxx` binding (which only
sees one anchor record) can't express it alone. The template's own
stored body is a wrapper/fallback only; don't expect editing it in the
UI to change the itemized content — that always comes from Python.

## Versioning

Bump `version` in `__manifest__.py` (format `19.0.{major}.{minor}.{patch}`)
and add an entry to `CHANGELOG.md` for any behavior change.
