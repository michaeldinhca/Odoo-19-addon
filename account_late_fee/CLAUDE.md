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
  one-time/recurring with cap, same-invoice/new-invoice).
- `account.late.fee` — one row per charged/pending `(invoice_line_id,
  period_index)` pair. That pair is the idempotency key, enforced by a
  DB unique constraint — the nightly cron must be safe to re-run.
- `description` on `account.late.fee` is the single source of truth for
  the human-readable explanation (invoice line label, new invoice line,
  and email body all read this same field — never regenerate the text
  in more than one place).

## Workflow

Cron (`_cron_generate_late_fees`, daily) only creates `draft` records.
Nothing posts or emails until a human calls `action_confirm()` — that is
the deliberate manual-review gate. `action_confirm()` auto-posts the
resulting invoice(s) immediately; there is no separate "post" step by
design, since the confirm click is the reviewed checkpoint.

`same_invoice` mode falls back to `new_invoice` automatically (not an
error) whenever the target invoice was already sent to the customer
(`is_move_sent`) or can't be reset to draft (`button_draft()` raises
`UserError` — hash-secured, locked, etc.). Never remove this fallback;
it exists specifically so a document the customer already has a copy of
is never silently altered.

## Versioning

Bump `version` in `__manifest__.py` (format `19.0.{major}.{minor}.{patch}`)
and add an entry to `CHANGELOG.md` for any behavior change.
