# Architecture and design decisions

This is the design record for `enterprise_remittance_management`: what was found in the Odoo 19 source,
what was decided because of it, and what the known limits are.

Source reviewed: the Community `account`, `mail`, `base` and `web` modules of the Odoo 19 tree used for
development (licence checked LGPL-3 before reading). No Enterprise-licensed source was read and the addon
depends on Community modules only (`account`, `mail`), so it installs on Community and on Enterprise
(Odoo.sh or self-hosted).

## 1. What native Odoo 19 does (verified by reading the code and by running it)

| Topic | Finding | Consequence for the design |
|---|---|---|
| Wizard flow | `account.payment.register.action_create_payments()` calls `_create_payments()`, which builds `to_process`: one dict per payment with `create_vals`, `to_reconcile` (the journal items) and `batch`, then runs `_init_payments()`, `_post_payments()`, `_reconcile_payments()`. After `_init_payments()`, `to_process[i]['payment']` is the payment created for exactly `to_process[i]['to_reconcile']`. | This is the authoritative payment to source-lines mapping. Vendor matching is never needed and cannot mis-assign payments of the same vendor. |
| Two create buttons | The form has two `action_create_payments` buttons with opposite `total_payments_amount` conditions. | Nothing to replace: the hook is on the model (`_reconcile_payments`), so both buttons, and any code calling `_create_payments()`, are covered. No XPath on those buttons. |
| Grouping | `group_payment` off: one payment per move (sub-batches keyed by `move_id`). On: one payment per batch (partner, account, currency, bank, partner type); inbound and outbound batches of a partner with a single bank merge. `installments_mode` can restrict `to_reconcile` to some lines. | `to_reconcile` per payment is what was really reconciled; the snapshot is per payment and holds only its own documents. |
| Offsets | `_reconcile_payments()` reconciles `payment lines + to_reconcile` in one `reconcile()` plan. A bill and a credit in the same plan are matched with each other (an "offset" partial) and the payment line is matched with what is left. | A grouped bill + bigger credit gives two partials: bill/credit offset (1,461.32) and credit/payment (723.87). The payment entry itself is reconciled with the credit only. `payment.reconciled_bill_ids` still lists the bill on a fresh read, but only through the `matched_payment_ids` link the wizard adds: a bare link with no amounts, no offset/payment split and no historical balances, lost when the payment is deleted, and absent when the offset was made before the payment. It is therefore never used as a source. |
| Signed amounts | `amount_residual` on payable lines is negative for a bill, positive for a credit. | The addon converts to the vendor view: bills positive, credits negative. |
| Exchange difference | An exchange move is created when rates differ. Its partial links the exchange move line to the **payment** line, so document-currency tie-out is unaffected. | Recorded as kind `exchange` in the ownership trail. |
| Reset to draft | In this Odoo 19 build `button_draft()` does not remove partial reconciles. | The addon does not depend on either behaviour (older builds remove them). |
| Cancel / delete | `action_cancel()` of a draft payment unlinks its move, which removes the payment partial only. `unlink()` needs a draft payment. The bill/credit offset is left in place. | This is the reported issue: after cancel or delete the bill stays offset and the credit only partly open, so the next registration hides the bill. |
| Unreconcile | `account.partial.reconcile.unlink()` reverses exchange and cash-basis entries itself, and is allowed to Billing users. | Reversal of an offset simply calls `unlink()` under the user's own rights: no accounting is rewritten by the addon. |
| Lock dates | `company._get_violated_lock_dates(date, has_tax, journal)`. | Used to refuse an automatic reversal in a locked period. |
| Report action | `report_action()` returns Odoo's one-time "configure document layout" wizard for a company without a layout. | Inherited as is by "Print Remittance Slip". |

## 2. Data model

Three models plus two wizards. All figures are stored copies; nothing is recomputed from live residuals.

```
account.payment  1 ---- 0..1  enterprise.remittance.registration  (audit anchor, mail.thread)
                                   | 1 ---- n  enterprise.remittance.allocation      (one line per document)
                                   | 1 ---- n  enterprise.remittance.reconciliation  (one row per partial reconcile created)
```

* **Registration** (`enterprise.remittance.registration`): one per payment created by the wizard. Justified
  because it (a) survives the deletion of the payment (`payment_id` is `ondelete set null`, every figure is a
  copy), so history is never orphaned; (b) carries the workflow state and the decision audit
  (user, date, reason, outcome) and the chatter; (c) groups payments created by one wizard run (`run_ref`).
* **Allocation** (`enterprise.remittance.allocation`): payment, vendor, source document, document type,
  original amount, previously settled, amount due before payment, payment applied, offset applied, total applied,
  remaining immediately after payment, currency, amount in payment currency and company currency.
  Sign convention in the document currency: bills positive, credits negative.
* **Reconciliation trail** (`enterprise.remittance.reconciliation`): every partial reconcile created by that
  registration, recorded by comparing the partials that touch the payment and source lines before and after the
  native `reconcile()`. Kind `payment`, `offset`, `exchange` or `other`. When the partial disappears the row
  stays and is stamped (who, when, through which path).

Constraints and indexes: `unique(payment_id)`; `unique(registration_id, move_id)`; indexes on payment,
partner, company, state, run reference, move, partial and line references. Access: read-only for every group
(Billing, Read-only accountant and above); rows are created by the trusted capture code only.
Immutability: `write()` refuses any change to snapshot columns, `unlink()` is refused except at module
uninstall.

## 3. Payment to batch mapping

`_reconcile_payments(to_process)` is overridden. Before calling `super()`, for each payment in scope
(`partner_type == 'supplier'`) it records the payable lines of every source document, their residuals, the
partials that already exist, and the payment's own payable lines. After `super()` it reads the partials that are
new and touch those lines, classifies them and stores everything, in a savepoint.

Applied amounts come from the partials actually created (never from a formula), so any native split is
reflected exactly. The document equation `due before - applied = remaining` and the payment equation
`settled = allocated + unallocated` are checked; a mismatch is written to `diagnostic` (or refuses the
registration when the company enables strict mode). A failure of the capture code never blocks a payment unless
strict mode is on.

## 4. Reconciliation ownership and cancellation

A partial belongs to a registration if and only if its id is in that registration's trail. Reconciliations that
existed before (visible as `original amount - amount due before payment`) or were made after are never owned.

Reset, cancel and delete of a payment with owned, still-existing offsets are guarded at both levels: the
payment methods and, as a second line, `button_draft`, `button_cancel` and `unlink` of the payment's journal
entry. Without a decision the user is redirected to a wizard (`RedirectWarning`); trusted code passes
`remittance_offset_decision` in the context. Payments without owned offsets, and payments never tracked, are not
interrupted.

* **Keep (default, Option A)**: the payment operation runs, the offsets stay, the decision is recorded.
* **Reverse (Option B)**: only offsets that pass every check are reversed, each with `partial.unlink()` under the
  user's rights (no sudo): the partial is still the recorded one (same lines and amount); both documents are
  posted; the user has every involved company enabled; no lock date is violated for either document; no
  reconciliation was made on those lines after the offset; the user has the unlink right. Accounting
  Administrator (`account.group_account_manager`) or Accountant (`account.group_account_user`) is required: in this
  Odoo 19 the Administrator role does not imply the "full features" Accountant flag, so both are accepted. Everything not eligible is kept and the reason is shown and logged.
* **Reverse retained offsets later**: the same checks from the remittance record, once the payment is inactive.

A payment must be reset to draft before it can be deleted (native rule); the wizard says so.

## 5. Report and email

* `ir.actions.report` "Print Remittance Slip" (`qweb-pdf`, bound to `account.payment`, vendor payments),
  template `report_remittance_slip`, built on `web.external_layout`. The paper format is the company's.
* The template only formats a plain structure built by `account.payment._remittance_slip_data()`: rows sorted by
  date, then reference; totals per currency; direction-aware wording; flags for remaining balances, draft and
  cancelled payments, legacy fallback.
* Legacy payments (no registration): built from the native reconciliation only when it fully explains the payment,
  clearly labelled, without balances before payment; otherwise no table is printed.
* Email template `Payment: Remittance Advice` on `account.payment` with the slip attached through
  `report_template_ids`, sent through the standard composer. Lines come from the snapshot, so an offset that
  preceded the payment cannot drop a line. The native payment receipt report and template are untouched.

## 6. Migration

`enterprise.remittance.migration.wizard` (Settings administrators only) reads legacy Studio data through
configurable technical names, in two accessor methods only, so a fresh installation never needs Studio.
Dry run first; malformed, ambiguous or inconsistent rows are reported and skipped; migrated lines are flagged
`split_known = False` (legacy data cannot say how much was paid versus offset). "Find Legacy Artifacts" lists
server actions, automation rules and views that mention the legacy names, and changes nothing.

## 7. Known limits

* Payments not created by the Register Payment wizard (manual payment reconciled from a bill, batch payments
  created elsewhere) have no snapshot and use the legacy fallback.
* Customer payments are out of scope by default (`_remittance_in_scope()` is the single extension point).
* Ownership cannot be proven for migrated data, so migrated offsets are never reversed automatically.
* `wkhtmltopdf` is required for PDF output, as for any Odoo report. The automated tests render the QWeb to HTML
  (Odoo's test mode); see the README for how PDF output was checked.
* The wizard does not undo reconciliations made after the offset; it refuses and explains.
