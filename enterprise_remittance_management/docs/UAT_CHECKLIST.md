# User acceptance checklist

Run on a staging database. Tick each line, note the payment number used.
Numbers below are examples: any bills and credits with the same relationships will do.

Preparation: Accounting app with a bank journal, a vendor with an email address, company document layout
configured (Settings, Companies, Configure Document Layout), `wkhtmltopdf` available.

## A. Capture

- [ ] **A1 Single bill.** Post a bill of 500.00, Register Payment, Create Payment. Open the payment, tab
      **Payment Allocation**: one line, type Vendor Bill, original 500.00, due before 500.00, applied 500.00,
      remaining 0.00.
- [ ] **A2 Two bills grouped.** Bills 80.08 and 9.67, tick Group Payments. One payment of 89.75 with two lines.
- [ ] **A3 Separate payments, same vendor.** Two bills, Group Payments off. Two payments; each shows only its own bill.
- [ ] **A4 Two vendors in one operation.** Select bills of two vendors, group. Two payments; each lists only its
      vendor's bills. Remittances menu: both records share the same Registration Run.
- [ ] **A5 Bill and larger credit.** Bill 1,461.32 and vendor credit 2,185.19, group. The payment is **Receive
      Money** of 723.87. Allocation shows the bill (applied 1,461.32, all offset) **and** the credit
      (-2,185.19, of which -723.87 by the payment). In the Reconciliation Trail the payment application is against
      the credit only; the bill is offset against the credit.
- [ ] **A6 Partial payment.** Two bills 500.00 and 300.00, group, change the amount to 600.00. The bill that is
      not fully paid shows a remaining balance and is highlighted.
- [ ] **A7 Earlier settlement.** Reconcile a credit with a bill first, then pay the bill. Original amount and
      amount due before payment differ; no offset is owned by the new record.
- [ ] **A8 Foreign currency.** Bill in a foreign currency, pay in the company currency. Document amounts stay in
      the bill currency; the paid share is shown in the payment currency.
- [ ] **A9 Immutability.** Edit the bill afterwards, or reverse its payment reconciliation: the allocation keeps
      the original figures. No field of the allocation is editable.

## B. Remittance slip (PDF)

- [ ] **B1** From a payment, Print, **Print Remittance Slip**. Title, vendor, payment date, reference, payment
      method, optional note (from the Payment Allocation tab), summary, tables, company header and footer.
- [ ] **B2** Summary: Bills Paid, Credits Applied (negative), Net Payment. Bills Paid plus Credits Applied equals
      the net payment; wording says received from or sent to the vendor correctly (A5 is "Received").
- [ ] **B3** Bills and credits are in separate tables, sorted by date then reference. Columns: Document Reference /
      Number, Date, Due Date, Original Amount, Amount Due Before Payment, Payment / Applied Amount, Remaining After Payment.
- [ ] **B4** Partial payment (A6): lines with a balance are highlighted and the footnote says so.
- [ ] **B5** Long selection (30 or more bills): the table header repeats on every page; no row is cut across pages.
- [ ] **B6** Foreign currency (A8): each amount carries its own currency symbol; no single symbol is used for both.
- [ ] **B7** Legacy payment (created before installation): the slip carries the notice that it is rebuilt from
      current reconciliation and has "n/a" for balances before payment. If the reconciliation does not explain the
      payment, no table is printed.
- [ ] **B8** A draft payment prints a DRAFT banner; a cancelled one prints CANCELLED.
- [ ] **B9** Settings, Accounting, Remittance Management, switch **Show Note on Remittance Slip** off: the note disappears.

## C. Email

- [ ] **C1** Payment form, **Send Remittance**: the composer opens with the vendor as recipient, subject containing
      the payment number, the body with a compact table (reference, date, original, due before, applied) and the
      slip attached as a PDF.
- [ ] **C2** For A5 the body lists the bill **and** the credit. Wording is direction aware.
- [ ] **C3** "Best regards" appears once: try a user signature that already contains it, one that does not, and none.
- [ ] **C4** Nothing internal in the email or the PDF (no approvals, no internal users, no technical ids).
- [ ] **C5** The native "Send receipt by email" and the native Payment Receipt report still work.

## D. Cancellation, reset, deletion

Use the A5 payment (it owns a bill/credit offset).

- [ ] **D1 Guard.** On the payment click **Reset to Draft** (and separately **Cancel**). A dialog explains the
      offsets and offers **Review Offsets**. Nothing changed yet.
- [ ] **D2 Wizard content.** Shows the payment, vendor, amount, both source documents and the reconciliation
      link (bill / credit, 1,461.32) with "Can be reversed".
- [ ] **D3 Keep (default).** Choose keep, enter a reason, Confirm. Payment is reset/cancelled. The bill is still
      offset, the credit shows 723.87 open. The Remittances record shows state, outcome "kept", user, date, reason;
      chatter logs it.
- [ ] **D4 Re-registration after keep.** Register the credit again: its line shows original -2,185.19, due before
      -723.87 and a note that 1,461.32 was already offset by the earlier record. The offset bill is not
      selectable (native behaviour), and the note explains why.
- [ ] **D5 Reverse now.** Repeat A5, cancel, choose **Reverse**. Bill and credit are open again for their
      full amounts; re-registering shows the true original balances.
- [ ] **D6 Reverse later.** After D3 on another payment, open the Remittances record, **Reverse Retained
      Offsets**, confirm with a reason.
- [ ] **D7 Blocked reversal.** Lock the accounting period up to the bill dates, repeat: the wizard says the
      offset is in a locked period, reverse is not offered, keep still works.
- [ ] **D8 Later activity.** After keeping the offset, pay the credit remainder, then try to reverse the older
      offset: refused ("reconciled again").
- [ ] **D9 Access.** A Billing user can cancel with keep but cannot reverse; an Accounting Administrator (even without
      the "full features" flag) can reverse; a Read-only accountant can read but not change anything.
- [ ] **D10 Other paths.** From the payment's journal entry, try Reset to Draft, Cancel Entry and Delete: each
      asks for the decision. Unreconcile from the bill's payment widget works as usual and is stamped in the trail.
- [ ] **D11 Delete.** Reset to draft (keep), delete the payment. The Remittances record stays (state Payment
      Deleted, all lines readable).
- [ ] **D12 No interruption.** A payment of a single bill (no offset) is reset, cancelled and deleted without any dialog.

## E. Multi-company and security

- [ ] **E1** A user of company A cannot see company B's remittance records (Remittances menu, search, direct link).
- [ ] **E2** With both companies enabled in the switcher both are visible; reversal of an offset of company B needs company B enabled.
- [ ] **E3** The **Debug** tab (vendor and document ids) is visible to Accounting Advisers only.

## F. Migration and cutover (only if legacy Studio data exists)

- [ ] **F1** Accounting, Configuration, **Legacy Allocation Migration** (Settings administrators). Check the field names.
- [ ] **F2** **Scan (Dry Run)**: counts and issues are plausible; malformed rows are listed, none invented.
- [ ] **F3** **Migrate**: records appear in Remittances with the Migrated ribbon; slips of those payments use them.
- [ ] **F4** **Find Legacy Artifacts** lists the old server actions, automation rules and QWeb report. Run both
      flows in parallel for a period. Disable the old artifacts **manually** only after validation.
