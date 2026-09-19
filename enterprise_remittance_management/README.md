# Enterprise Remittance Management

`enterprise_remittance_management` for Odoo 19 (Community or Enterprise, Odoo.sh or self-hosted).
Author: NGYN Solutions Inc. Licence: LGPL-3. Depends on `account` and `mail` only.

It records exactly which vendor bills and credits every payment settled, keeps that history immutable, prints a
professional **Remittance Slip** (PDF), emails it to the vendor, and gives accountants a controlled way to reset,
cancel or delete a payment without leaving confusing bill/credit offsets behind.

Design record: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Acceptance script: [docs/UAT_CHECKLIST.md](docs/UAT_CHECKLIST.md).

## What it does

1. **Allocation snapshot, captured inside the native Register Payment flow.** For every vendor payment created
   by the wizard, one record with one line per bill or credit: original amount, amount due before payment,
   applied amount (paid by the payment, and offset against another document, shown separately), remaining
   immediately after payment, document type, currency. Bills are positive, credits negative.
2. **Exact mapping.** The wizard's own pairing of each created payment with its journal items is used, so several
   payments of one vendor, several vendors in one operation, grouped or separate payments, partial payments,
   inbound (credit larger than bills) and outbound payments, multi-currency and multi-company all work. Native
   payment accounting is untouched.
3. **Ownership trail** of every reconciliation the registration created, so a bill/credit offset made by that
   registration can be told apart from any other reconciliation.
4. **Controlled reset, cancel, delete** of a payment that owns offsets: keep them (default) or reverse only what
   is provably owned and safe to reverse. Every decision records user, date, reason and outcome, and is logged in the chatter.
5. **Remittance Slip** (QWeb PDF, `Print` menu of vendor payments) and **remittance email** with the slip attached.
6. **Optional migration** of legacy Studio allocation data, and a scanner listing legacy artifacts (never disables anything).

## Install and configure

1. Add the folder to the addons path, update the apps list, install **Enterprise Remittance Management**.
2. Settings, Accounting, **Remittance Management** (per company):
   * *Record Payment Allocations* (on by default): the switch for the whole capture.
   * *Strict Allocation Check* (off): refuse a registration whose allocation does not tie out. When off, the
     mismatch is recorded as a diagnostic and the payment is created normally.
   * *Show Note on Remittance Slip* (on): prints the optional **Remittance Note** of the payment.
3. Configure the company document layout once (Odoo asks on the first print). The slip uses the company paper
   format (A4 or Letter) and `web.external_layout`. PDF output needs `wkhtmltopdf`, as for any Odoo report.

No view on the Register Payment wizard is modified: capture is a model-level hook, so the two native
"Create Payment" buttons and any code calling `_create_payments()` are all covered.

## Where things are

| Where | What |
|---|---|
| Payment form, tab **Payment Allocation** | Bill/credit reference, date, due date, original, due before payment, applied, remaining after payment, type, View Document; reconciliation trail (Administrators and Accountants); remittance note; debug ids (Advisers) |
| Payment form, **Send Remittance**; Print, **Print Remittance Slip** | Email with PDF; the PDF |
| Accounting, Vendors, **Remittances** | Records with state, diagnostics, retained-offset filter; form with allocations, trail, cancellation audit, chatter |
| Accounting, Configuration, **Legacy Allocation Migration** | Migration wizard (Settings administrators; the Configuration menu also needs Accounting Adviser) |

## Reset, cancel, delete: how the decision works

Odoo natively removes only the payment's own reconciliation when a payment is cancelled or deleted. When the
payment was registered from bills **and** credits together, the bill/credit offset stays: the bill looks paid,
the credit is only partly open, and the next registration hides the bill.

| Situation | Behaviour |
|---|---|
| Payment has no owned offset, or was never tracked | Nothing changes: no dialog |
| Reset, cancel or delete, offsets owned | A dialog sends the user to the decision wizard. Buttons, list actions, server code and the payment's journal entry (`button_draft`, `button_cancel`, `unlink`) are all guarded |
| **Keep** (default) | The operation runs, offsets stay, decision recorded |
| **Reverse** (Accounting Administrator or Accountant) | Each offset is reversed only if: still the recorded reconciliation; both documents posted; every involved company enabled; no lock date violated; no later reconciliation on those lines; unlink right. Others are kept with the reason shown |
| **Reverse Retained Offsets** (on the record) | Same checks, later, once the payment is inactive |

A payment must be reset to draft before deletion (native rule). Trusted code can pass the context keys
`remittance_offset_decision` (`keep` or `reverse`) and `remittance_reason`.

## Data model

* `enterprise.remittance.registration`: per payment; survives payment deletion; state, decision audit, diagnostics, chatter.
* `enterprise.remittance.allocation`: per document; immutable amounts.
* `enterprise.remittance.reconciliation`: per partial reconcile created; removal audit.

Snapshot columns cannot be written or deleted (not even by administrators); end users have read-only access.
Records are created by the capture code with a narrow, commented `sudo()`, audit stamps likewise.
Multi-company record rules follow the native payment rule. Debug ids are limited to Accounting Advisers.

## Migration from Studio

Wizard **Legacy Allocation Migration**. Names of the legacy model and fields are configurable (defaults match a
typical Studio build). **Scan (Dry Run)** first. Rows that are malformed, ambiguous or inconsistent
(before minus applied is not remaining, wrong sign convention, snapshot disagreeing with the line, snapshot entry with
no line, duplicates) are reported and left out; nothing is invented. Migrated lines have *Payment/Offset Split
Known* unticked. **Find Legacy Artifacts** lists server actions, automation rules and views mentioning the legacy
names.

Cutover suggestion: install, run both flows in parallel (the old server action that calls the native
`action_create_payments()` keeps working), migrate, validate with the UAT checklist, then **manually** disable the
old artifacts. In the originating deployment these were server actions 2107, 2759 and 2760 and automation 149
(database-specific ids, given only as examples; rely on the scanner). Fresh installations never need Studio.

## Limits

* Payments not created by the Register Payment wizard have no snapshot: the slip falls back to the current
  reconciliation, clearly labelled and only when it explains the payment.
* Customer payments are not tracked (`account.payment.register._remittance_in_scope()` is the extension point).
* Ownership is unknown for migrated data, so its offsets are never reversed automatically.
* Setting the company paper format is the way to choose A4 or Letter.
* The automated tests render the QWeb to HTML (Odoo's test mode). The real PDF was also rendered during development with the official patched `wkhtmltopdf` 0.12.6.1: company header and footer, repeated table header on every page, no split rows. An unpatched `wkhtmltopdf` (for example the Debian package) ignores the header and footer, as for any Odoo report.

## Tests

`--test-tags /enterprise_remittance_management`, database with Accounting installed (generic chart used by the tests).
99 tests: capture (selection shapes, credits, partial, write-off, overpayment, multi-currency, exchange difference,
3-decimal precision, immutability, exception and strict paths), cancellation (guard on every path, keep, reverse,
locked period, later activity, wizard, rights, re-registration), report and email (rendered structure, sorting,
signs, flags, multi-currency labels, legacy fallbacks, composer attachment), security and multi-company, migration and parser.
