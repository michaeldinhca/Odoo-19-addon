from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.enterprise_remittance_management.models.account_payment_register import AccountPaymentRegister

from .common import RemittanceCommon


@tagged('post_install', '-at_install')
class TestRegistrationCapture(RemittanceCommon):

    # ------------------------------------------------------------------
    # Selection shapes
    # ------------------------------------------------------------------
    def test_single_bill(self):
        bill = self._bill(self.vendor_a, 500.0, ref='V-INV-1')
        payment = self._register(bill)

        registration = self._registration(payment)
        self.assertEqual(registration.name, payment.name)
        self.assertEqual(registration.partner_id, self.vendor_a)
        self.assertEqual(registration.payment_type, 'outbound')
        self.assertEqual(registration.state, 'active')
        self.assertEqual(registration.origin, 'registered')
        self.assertEqual(registration.net_amount, 500.0)
        self.assertEqual(registration.settled_amount, 500.0)
        self.assertEqual(registration.writeoff_amount, 0.0)
        self.assertEqual(registration.unallocated_amount, 0.0)
        self.assertFalse(registration.has_diagnostic)

        line = self._line(registration, bill)
        self.assertLine(line, original=500.0, due_before=500.0, applied=500.0, remaining=0.0,
                        payment_applied=500.0, offset_applied=0.0)
        self.assertEqual(line.document_type, 'bill')
        self.assertEqual(line.document_ref, 'V-INV-1')
        self.assertEqual(line.vendor_id, self.vendor_a)
        self.assertEqual(line.payment_amount, 500.0)
        self.assertEqual(registration.debug_snapshot, '%s|%s|500.00' % (self.vendor_a.id, bill.id))
        self.assertEqual(registration.reconciliation_ids.mapped('kind'), ['payment'])
        self.assertEqual(payment.remittance_registration_id, registration)

    def test_button_entry_point_captures_too(self):
        """Both native 'Create Payment' buttons call action_create_payments(): no view change is needed."""
        bill = self._bill(self.vendor_a, 120.0)
        action = self._wizard(bill).action_create_payments()
        payment = self.env['account.payment'].browse(action['res_id'])
        self.assertTrue(self._registration(payment))

    def test_grouped_bills_outbound_example(self):
        bill_1 = self._bill(self.vendor_a, 80.08, ref='B1')
        bill_2 = self._bill(self.vendor_a, 9.67, ref='B2')
        payment = self._register(bill_1 | bill_2, group=True)

        self.assertEqual(payment.amount, 89.75)
        registration = self._registration(payment)
        self.assertEqual(len(registration.allocation_ids), 2)
        self.assertLine(self._line(registration, bill_1), original=80.08, due_before=80.08, applied=80.08, remaining=0.0)
        self.assertLine(self._line(registration, bill_2), original=9.67, due_before=9.67, applied=9.67, remaining=0.0)
        self.assertEqual(sum(registration.allocation_ids.mapped('amount_applied')), 89.75)
        self.assertEqual(registration.net_amount, 89.75)

    def test_multiple_vendors_one_operation(self):
        a_1 = self._bill(self.vendor_a, 100.0, ref='A1')
        a_2 = self._bill(self.vendor_a, 50.0, ref='A2')
        b_1 = self._bill(self.vendor_b, 70.0, ref='B1')
        payments = self._register(a_1 | a_2 | b_1, group=True)

        self.assertEqual(len(payments), 2)
        by_vendor = {payment.partner_id: self._registration(payment) for payment in payments}
        self.assertEqual(by_vendor[self.vendor_a].allocation_ids.move_id, a_1 | a_2)
        self.assertEqual(by_vendor[self.vendor_b].allocation_ids.move_id, b_1)
        self.assertEqual(by_vendor[self.vendor_a].net_amount, 150.0)
        self.assertEqual(by_vendor[self.vendor_b].net_amount, 70.0)
        # Payments created by one wizard run share a run reference.
        self.assertEqual(len(set(payments.remittance_registration_ids.mapped('run_ref'))), 1)
        self.assertTrue(payments.remittance_registration_ids[0].run_ref)

    def test_separate_payments_same_vendor_get_only_their_own_bill(self):
        """Vendor matching alone would attach both bills to both payments: the wizard mapping does not."""
        bill_1 = self._bill(self.vendor_a, 100.0, ref='B1')
        bill_2 = self._bill(self.vendor_a, 50.0, ref='B2')
        payments = self._register(bill_1 | bill_2, group=False)

        self.assertEqual(len(payments), 2)
        self.assertEqual(payments.partner_id, self.vendor_a)
        for payment in payments:
            registration = self._registration(payment)
            self.assertEqual(len(registration.allocation_ids), 1)
            expected_bill = bill_1 if payment.amount == 100.0 else bill_2
            self.assertEqual(registration.allocation_ids.move_id, expected_bill)
            self.assertEqual(registration.allocation_ids.amount_applied, payment.amount)

    # ------------------------------------------------------------------
    # Credits
    # ------------------------------------------------------------------
    def test_mixed_bill_and_larger_credit_is_an_inbound_payment(self):
        bill = self._bill(self.vendor_a, 1461.32, ref='BILL-1')
        credit = self._credit(self.vendor_a, 2185.19, ref='CN-1')
        payment = self._register(bill | credit, group=True)

        self.assertEqual(payment.payment_type, 'inbound')
        self.assertEqual(payment.amount, 723.87)
        # Why the snapshot exists: the payment entry itself is reconciled with the credit only. The bill was
        # offset against the credit, so nothing but this record says what was offset and what was paid.
        self.assertEqual(self._documents_reconciled_with_payment(payment), credit)

        registration = self._registration(payment)
        self.assertEqual(registration.net_amount, -723.87)
        self.assertEqual(registration.settled_amount, -723.87)
        self.assertAlmostEqual(registration.unallocated_amount, 0.0)
        bill_line = self._line(registration, bill)
        credit_line = self._line(registration, credit)
        self.assertLine(bill_line, original=1461.32, due_before=1461.32, applied=1461.32, remaining=0.0,
                        payment_applied=0.0, offset_applied=1461.32)
        self.assertLine(credit_line, original=-2185.19, due_before=-2185.19, applied=-2185.19, remaining=0.0,
                        payment_applied=-723.87, offset_applied=-1461.32)
        self.assertEqual(credit_line.document_type, 'credit')
        # Signed applied amounts add up to the net payment.
        self.assertAlmostEqual(sum(registration.allocation_ids.mapped('amount_applied')), -723.87)
        self.assertAlmostEqual(sum(registration.allocation_ids.mapped('payment_amount')), registration.settled_amount)
        kinds = sorted(registration.reconciliation_ids.mapped('kind'))
        self.assertEqual(kinds, ['offset', 'payment'])
        offset = registration.reconciliation_ids.filtered(lambda row: row.kind == 'offset')
        self.assertEqual(offset.amount, 1461.32)
        self.assertEqual(offset.partial_id.id, offset.partial_ref)

    def test_bill_larger_than_credit_is_an_outbound_payment(self):
        bill = self._bill(self.vendor_a, 500.0, ref='B')
        credit = self._credit(self.vendor_a, 120.0, ref='C')
        payment = self._register(bill | credit, group=True)

        self.assertEqual((payment.payment_type, payment.amount), ('outbound', 380.0))
        registration = self._registration(payment)
        self.assertLine(self._line(registration, bill), original=500.0, due_before=500.0, applied=500.0, remaining=0.0,
                        payment_applied=380.0, offset_applied=120.0)
        self.assertLine(self._line(registration, credit), original=-120.0, due_before=-120.0, applied=-120.0,
                        remaining=0.0, payment_applied=0.0, offset_applied=-120.0)
        self.assertEqual(registration.net_amount, 380.0)

    # ------------------------------------------------------------------
    # Partial payments and earlier settlements
    # ------------------------------------------------------------------
    def test_partial_payment_of_bills_and_a_credit(self):
        bill_1 = self._bill(self.vendor_a, 500.0, ref='B1')
        bill_2 = self._bill(self.vendor_a, 300.0, ref='B2')
        credit = self._credit(self.vendor_a, 100.0, ref='C1')
        payment = self._register(bill_1 | bill_2 | credit, group=True, amount=450.0)

        self.assertEqual(payment.amount, 450.0)
        registration = self._registration(payment)
        lines = registration.allocation_ids
        self.assertFalse(registration.has_diagnostic)
        # Whatever way the native reconcile splits it, every line ties out and the total is the payment.
        for line in lines:
            self.assertAlmostEqual(line.amount_due_before - line.amount_applied, line.amount_remaining)
        self.assertAlmostEqual(sum(lines.mapped('amount_applied')), 450.0)
        self.assertAlmostEqual(sum(lines.mapped('amount_remaining')), 250.0)
        self.assertAlmostEqual(sum(lines.mapped('payment_amount')), 450.0)
        self.assertEqual(lines.filtered('has_remaining').mapped('document_type'), ['bill'])

    def test_amounts_settled_before_the_payment_are_not_this_registrations_offsets(self):
        bill = self._bill(self.vendor_a, 1000.0, ref='B')
        credit = self._credit(self.vendor_a, 300.0, ref='C')
        (bill | credit).line_ids.filtered(lambda line: line.account_type == 'liability_payable').reconcile()
        self.assertEqual(bill.amount_residual, 700.0)
        earlier_partials = (bill | credit).line_ids.matched_debit_ids | (bill | credit).line_ids.matched_credit_ids

        payment = self._register(bill)

        registration = self._registration(payment)
        line = self._line(registration, bill)
        self.assertLine(line, original=1000.0, due_before=700.0, applied=700.0, remaining=0.0,
                        payment_applied=700.0, offset_applied=0.0)
        self.assertEqual(line.previously_settled_amount, 300.0)
        # The earlier offset is not owned by this registration, so it can never be reversed by it.
        self.assertFalse(set(earlier_partials.ids) & set(registration.reconciliation_ids.mapped('partial_ref')))
        self.assertFalse(registration._remittance_active_offsets())

    def test_write_off_is_explained_not_flagged(self):
        bill = self._bill(self.vendor_a, 500.0, ref='B')
        wizard = self._wizard(bill, amount=450.0)
        self.assertTrue(wizard.show_payment_difference)
        wizard.write({'payment_difference_handling': 'reconcile', 'writeoff_account_id': self.expense_account.id})
        payment = wizard._create_payments()

        registration = self._registration(payment)
        self.assertEqual(registration.net_amount, 450.0)
        self.assertEqual(registration.settled_amount, 500.0)
        self.assertEqual(registration.writeoff_amount, 50.0)
        self.assertFalse(registration.has_diagnostic)
        self.assertLine(self._line(registration, bill), original=500.0, due_before=500.0, applied=500.0, remaining=0.0)

    def test_overpayment_left_open_is_reported_as_unallocated(self):
        bill = self._bill(self.vendor_a, 500.0, ref='B')
        payment = self._register(bill, amount=650.0)

        registration = self._registration(payment)
        self.assertEqual(registration.net_amount, 650.0)
        self.assertEqual(registration.unallocated_amount, 150.0)
        self.assertLine(self._line(registration, bill), original=500.0, due_before=500.0, applied=500.0, remaining=0.0)

    # ------------------------------------------------------------------
    # Currencies and precision
    # ------------------------------------------------------------------
    def test_multicurrency_payment_in_document_currency(self):
        eur = self.setup_other_currency('EUR')
        bill = self._bill(self.vendor_a, 300.0, ref='EUR-1', currency=eur)
        payment = self._register(bill)

        self.assertEqual(payment.currency_id, eur)
        registration = self._registration(payment)
        line = self._line(registration, bill)
        self.assertEqual(line.currency_id, eur)
        self.assertLine(line, original=300.0, due_before=300.0, applied=300.0, remaining=0.0)
        self.assertEqual(line.payment_amount, 300.0)
        self.assertEqual(line.applied_amount_company, 150.0)
        self.assertEqual(registration.currency_id, eur)
        self.assertFalse(registration.has_diagnostic)

    def test_multicurrency_payment_in_company_currency(self):
        eur = self.setup_other_currency('EUR')
        bill = self._bill(self.vendor_a, 300.0, ref='EUR-1', currency=eur)
        payment = self._register(bill, currency=self.company.currency_id)

        self.assertEqual(payment.currency_id, self.company.currency_id)
        self.assertEqual(payment.amount, 150.0)
        registration = self._registration(payment)
        line = self._line(registration, bill)
        # Document figures stay in the document currency, the payment share is in the payment currency.
        self.assertEqual(line.currency_id, eur)
        self.assertLine(line, original=300.0, due_before=300.0, applied=300.0, remaining=0.0)
        self.assertEqual(line.payment_currency_id, self.company.currency_id)
        self.assertEqual(line.payment_amount, 150.0)
        self.assertEqual(registration.net_amount, 150.0)
        self.assertFalse(registration.has_diagnostic)

    def test_exchange_difference_does_not_break_the_tie_out(self):
        eur = self.setup_other_currency('EUR')
        bill = self._bill(self.vendor_a, 300.0, ref='OLD-EUR', currency=eur, date='2016-06-01')
        payment = self._register(bill)

        registration = self._registration(payment)
        line = self._line(registration, bill)
        self.assertLine(line, original=300.0, due_before=300.0, applied=300.0, remaining=0.0)
        self.assertFalse(registration.has_diagnostic, registration.diagnostic)
        # 300 EUR at 3.0 (100 in company currency) paid at 2.0 (150): the difference is an exchange entry.
        kinds = sorted(registration.reconciliation_ids.mapped('kind'))
        self.assertEqual(kinds, ['exchange', 'payment'])
        self.assertEqual(line.applied_amount_company, 100.0)

    def test_three_decimal_currency_precision(self):
        kwd = self.setup_other_currency('KWD', rounding=0.001)
        self.assertEqual(kwd.decimal_places, 3)
        bill_1 = self._bill(self.vendor_a, 33.333, ref='K1', currency=kwd)
        bill_2 = self._bill(self.vendor_a, 66.667, ref='K2', currency=kwd)
        payment = self._register(bill_1 | bill_2, group=True)

        self.assertEqual(payment.amount, 100.0)
        registration = self._registration(payment)
        self.assertLine(self._line(registration, bill_1), original=33.333, due_before=33.333, applied=33.333, remaining=0.0)
        self.assertLine(self._line(registration, bill_2), original=66.667, due_before=66.667, applied=66.667, remaining=0.0)
        self.assertEqual(kwd.round(sum(registration.allocation_ids.mapped('amount_applied'))), 100.0)
        self.assertFalse(registration.has_diagnostic)

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------
    def test_snapshot_is_immutable(self):
        bill = self._bill(self.vendor_a, 500.0, ref='B')
        payment = self._register(bill)
        registration = self._registration(payment)
        line = registration.allocation_ids
        trail = registration.reconciliation_ids

        with self.assertRaises(UserError):
            line.write({'amount_applied': 1.0})
        with self.assertRaises(UserError):
            registration.write({'net_amount': 1.0})
        with self.assertRaises(UserError):
            registration.write({'partner_id': self.vendor_b.id})
        with self.assertRaises(UserError):
            trail.write({'amount': 1.0})
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            registration.unlink()
        with self.assertRaises(UserError):
            trail.unlink()
        # Only workflow/audit columns can move.
        registration.sudo().write({'cancel_reason': 'allowed'})

    def test_historical_values_do_not_follow_live_residuals(self):
        bill = self._bill(self.vendor_a, 500.0, ref='B')
        payment = self._register(bill)
        registration = self._registration(payment)
        self.assertEqual(bill.amount_residual, 0.0)

        # Reopen the bill through a reversal of the payment reconciliation: live residual moves, history does not.
        bill.line_ids.remove_move_reconcile()
        self.assertEqual(bill.amount_residual, 500.0)
        line = self._line(registration, bill)
        self.assertLine(line, original=500.0, due_before=500.0, applied=500.0, remaining=0.0)

    # ------------------------------------------------------------------
    # Switches and exception paths
    # ------------------------------------------------------------------
    def test_capture_can_be_disabled_per_company(self):
        self.company.remittance_capture_enabled = False
        bill = self._bill(self.vendor_a, 100.0)
        payment = self._register(bill)

        self.assertFalse(payment.remittance_registration_ids)
        self.assertEqual(payment.state, 'paid')

    def test_customer_payments_are_out_of_scope(self):
        customer_invoice = self._make_move(self.vendor_a, 'out_invoice', 100.0, ref='INV')
        payment = self._register(customer_invoice)

        self.assertEqual(payment.partner_type, 'customer')
        self.assertFalse(payment.remittance_registration_ids)

    def test_capture_failure_never_blocks_the_payment(self):
        bill = self._bill(self.vendor_a, 100.0)
        with patch.object(AccountPaymentRegister, '_remittance_trail_vals', side_effect=ValueError('boom')), \
                self.assertLogs('odoo.addons.enterprise_remittance_management', level='ERROR'):
            payment = self._register(bill)

        self.assertEqual(payment.state, 'paid')
        self.assertFalse(payment.remittance_registration_ids)
        self.assertIn('could not be recorded', ' '.join(payment.message_ids.mapped('body')))

    def test_capture_failure_blocks_the_payment_in_strict_mode(self):
        self.company.remittance_strict_mode = True
        bill = self._bill(self.vendor_a, 100.0)
        with patch.object(AccountPaymentRegister, '_remittance_trail_vals', side_effect=ValueError('boom')):
            with self.assertRaises(UserError):
                self._register(bill)

    def _tamper_due_before(self, amount):
        original = AccountPaymentRegister._remittance_read_before

        def tampered(register, payment, lines, run_ref):
            snapshot = original(register, payment, lines, run_ref)
            for doc in snapshot['docs'].values():
                doc['due_before'] += amount
            return snapshot

        return patch.object(AccountPaymentRegister, '_remittance_read_before', tampered)

    def test_unexplained_mismatch_is_recorded_as_a_diagnostic(self):
        bill = self._bill(self.vendor_a, 100.0, ref='B')
        with self._tamper_due_before(10.0):
            payment = self._register(bill)

        registration = self._registration(payment)
        self.assertTrue(registration.has_diagnostic)
        self.assertIn(bill.display_name, registration.diagnostic)
        self.assertTrue(self._line(registration, bill).diagnostic)
        # Nothing is fabricated: the stored remaining is what the accounting really says.
        self.assertEqual(self._line(registration, bill).amount_remaining, 0.0)

    def test_unexplained_mismatch_is_refused_in_strict_mode(self):
        self.company.remittance_strict_mode = True
        bill = self._bill(self.vendor_a, 100.0, ref='B')
        with self._tamper_due_before(10.0), self.assertRaises(UserError):
            self._register(bill)
        self.assertEqual(bill.payment_state, 'not_paid')

    def test_chatter_note_on_the_payment(self):
        bill = self._bill(self.vendor_a, 100.0)
        payment = self._register(bill)
        self.assertIn('Remittance allocation recorded', ' '.join(payment.message_ids.mapped('body')))
