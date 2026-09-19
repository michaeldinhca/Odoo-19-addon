from datetime import timedelta

from odoo import Command
from odoo.exceptions import AccessError, RedirectWarning, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import RemittanceCommon


@tagged('post_install', '-at_install')
class TestCancellation(RemittanceCommon):
    """A bill and a bigger credit registered together produce a bill/credit offset next to the payment.
    Natively that offset survives the cancellation or deletion of the payment; these tests pin how the
    addon lets the accountant decide, and that nothing is reversed without an explicit, provable choice."""

    def setUp(self):
        super().setUp()
        self.bill = self._bill(self.vendor_a, 1461.32, ref='BILL-1')
        self.credit = self._credit(self.vendor_a, 2185.19, ref='CN-1')
        self.payment = self._register(self.bill | self.credit, group=True)
        self.registration = self._registration(self.payment)
        self.offset = self.registration.reconciliation_ids.filtered(lambda row: row.kind == 'offset')
        self.assertEqual(len(self.offset), 1)

    def _decide(self, payments, decision, reason='Entered by mistake'):
        return payments.with_context(remittance_offset_decision=decision, remittance_reason=reason)

    # ------------------------------------------------------------------
    # The guard
    # ------------------------------------------------------------------
    def test_every_destructive_payment_action_asks_for_a_decision(self):
        for method in ('action_draft', 'action_cancel', 'unlink'):
            with self.subTest(method=method), self.assertRaises(RedirectWarning) as raised:
                getattr(self.payment, method)()
            action = raised.exception.args[1]
            self.assertEqual(action['res_model'], 'enterprise.remittance.cancel.wizard')
            expected_operation = {'action_draft': 'draft', 'action_cancel': 'cancel', 'unlink': 'delete'}[method]
            self.assertEqual(action['context']['default_operation'], expected_operation)
            # Nothing happened.
            self.assertEqual(self.payment.state, 'paid')
            self.assertEqual(self.registration.state, 'active')
            self.assertEqual(self.offset.reversal_status, 'blocked')

    def test_journal_entry_paths_cannot_bypass_the_guard(self):
        move = self.payment.move_id
        for method in ('button_draft', 'button_cancel', 'unlink'):
            with self.subTest(method=method), self.assertRaises(RedirectWarning):
                getattr(move, method)()
        self.assertEqual(move.state, 'posted')
        # An explicit decision is accepted on the same path.
        move.with_context(remittance_offset_decision='keep').button_draft()
        self.assertEqual(move.state, 'draft')

    def test_second_destructive_step_asks_again(self):
        self._decide(self.payment, 'keep').action_draft()
        self.assertEqual(self.registration.state, 'draft')
        with self.assertRaises(RedirectWarning):
            self.payment.action_cancel()

    def test_payments_without_owned_offsets_are_not_interrupted(self):
        bill = self._bill(self.vendor_b, 100.0, ref='B')
        payment = self._register(bill)
        registration = self._registration(payment)

        payment.action_cancel()

        self.assertEqual(payment.state, 'canceled')
        self.assertEqual(registration.state, 'cancelled')
        self.assertEqual(registration.cancel_outcome, 'not_applicable')
        self.assertEqual(registration.cancel_operation, 'cancel')
        self.assertEqual(bill.amount_residual, 100.0)

    def test_payments_never_tracked_are_not_interrupted(self):
        untracked = self.env['account.payment'].create({
            'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': self.vendor_b.id,
            'amount': 10.0, 'journal_id': self.company_data['default_journal_bank'].id,
        })
        untracked.action_post()
        untracked.action_cancel()
        self.assertEqual(untracked.state, 'canceled')

    # ------------------------------------------------------------------
    # Keep (safe default)
    # ------------------------------------------------------------------
    def test_cancel_keeping_the_offsets(self):
        self._decide(self.payment, 'keep', reason='Wrong bank account').action_cancel()

        self.assertEqual(self.payment.state, 'canceled')
        self.assertEqual(self.registration.state, 'cancelled')
        self.assertEqual(self.registration.cancel_operation, 'cancel')
        self.assertEqual(self.registration.cancel_outcome, 'kept')
        self.assertEqual(self.registration.cancel_user_id, self.env.user)
        self.assertTrue(self.registration.cancel_date)
        self.assertEqual(self.registration.cancel_reason, 'Wrong bank account')
        # The natural leftovers of native behaviour: bill still offset, credit only partly open.
        self.assertEqual(self.bill.amount_residual, 0.0)
        self.assertEqual(self.credit.amount_residual, 723.87)
        self.assertEqual(len(self.registration._remittance_active_offsets()), 1)
        payment_row = self.registration.reconciliation_ids.filtered(lambda row: row.kind == 'payment')
        self.assertFalse(payment_row.partial_id)
        self.assertEqual(payment_row.removed_via, 'payment_cancel')
        messages = ' '.join(self.registration.message_ids.mapped('body'))
        self.assertIn('Wrong bank account', messages)
        self.assertIn('kept', messages.lower())

    def test_reset_to_draft_keeping_the_offsets(self):
        self._decide(self.payment, 'keep').action_draft()
        self.assertEqual(self.payment.state, 'draft')
        self.assertEqual(self.registration.state, 'draft')
        self.assertEqual(self.registration.cancel_operation, 'draft')
        self.assertEqual(self.registration.cancel_outcome, 'kept')

    def _reset_then_delete(self, delete_decision='keep', reset_decision='keep'):
        """Odoo only deletes a draft payment: the realistic sequence is reset first, then delete."""
        self._decide(self.payment, reset_decision, reason='Reset first').action_draft()
        self._decide(self.payment, delete_decision, reason='Duplicate').unlink()

    def test_delete_keeping_the_offsets_preserves_the_history(self):
        payment_name = self.payment.name
        self._reset_then_delete()

        registration = self.registration
        self.assertFalse(self.payment.exists())
        self.assertEqual(registration.state, 'deleted')
        self.assertFalse(registration.payment_id)
        self.assertEqual(registration.name, payment_name)
        self.assertEqual(registration.cancel_operation, 'delete')
        # Not orphaned: the snapshot is complete and still readable.
        self.assertEqual(len(registration.allocation_ids), 2)
        self.assertEqual(registration.partner_id, self.vendor_a)
        self.assertEqual(registration.net_amount, -723.87)
        self.assertLine(self._line(registration, self.credit), original=-2185.19, due_before=-2185.19,
                        applied=-2185.19, remaining=0.0)

    def test_reregistration_after_delete_explains_the_retained_offset(self):
        payment_name = self.payment.name
        self._reset_then_delete()

        # The confusing native behaviour: the offset bill can no longer be selected.
        with self.assertRaises(UserError):
            self._wizard(self.bill)
        new_payment = self._register(self.credit)

        self.assertEqual((new_payment.payment_type, new_payment.amount), ('inbound', 723.87))
        registration = self._registration(new_payment)
        line = self._line(registration, self.credit)
        self.assertLine(line, original=-2185.19, due_before=-723.87, applied=-723.87, remaining=0.0)
        self.assertEqual(line.previously_settled_amount, -1461.32)
        self.assertIn(payment_name, line.previous_settlement_note)

    # ------------------------------------------------------------------
    # Reverse (only what is provably owned and safe)
    # ------------------------------------------------------------------
    def test_cancel_reversing_the_owned_offset_restores_the_documents(self):
        self._decide(self.payment, 'reverse', reason='Payment issued in error').action_cancel()

        self.assertEqual(self.registration.cancel_outcome, 'reversed')
        self.assertEqual(self.bill.amount_residual, 1461.32)
        self.assertEqual(self.credit.amount_residual, 2185.19)
        self.assertFalse(self.registration._remittance_active_offsets())
        self.assertFalse(self.offset.partial_id)
        self.assertEqual(self.offset.removed_via, 'reversed_by_user')
        self.assertEqual(self.offset.removed_by_id, self.env.user)
        self.assertTrue(self.offset.removed_on)
        self.assertIn('Reversed', ' '.join(self.registration.message_ids.mapped('body')))

        # Re-registration starts from the true, original balances and is not hidden by leftovers.
        new_payment = self._register(self.bill | self.credit, group=True)
        registration = self._registration(new_payment)
        self.assertLine(self._line(registration, self.bill), original=1461.32, due_before=1461.32, applied=1461.32,
                        remaining=0.0)
        self.assertFalse(self._line(registration, self.bill).previous_settlement_note)
        self.assertEqual(new_payment.amount, 723.87)

    def test_reset_to_draft_reversing_the_owned_offset(self):
        self._decide(self.payment, 'reverse').action_draft()
        self.assertEqual(self.registration.state, 'draft')
        self.assertEqual(self.registration.cancel_outcome, 'reversed')
        self.assertEqual(self.bill.amount_residual, 1461.32)

    def test_delete_reversing_the_owned_offset(self):
        self._reset_then_delete(reset_decision='keep', delete_decision='reverse')
        self.assertEqual(self.registration.state, 'deleted')
        self.assertEqual(self.registration.cancel_outcome, 'reversed')
        self.assertEqual(self.bill.amount_residual, 1461.32)
        self.assertEqual(self.credit.amount_residual, 2185.19)

    def test_offsets_reversed_at_reset_leave_nothing_to_decide_at_delete(self):
        self._decide(self.payment, 'reverse').action_draft()
        self.payment.unlink()   # no decision needed any more
        self.assertEqual(self.registration.state, 'deleted')
        self.assertEqual(self.registration.cancel_operation, 'delete')
        self.assertEqual(self.registration.cancel_outcome, 'not_applicable')
        self.assertEqual(self.bill.amount_residual, 1461.32)
        self.assertEqual(self.credit.amount_residual, 2185.19)

    def test_a_posted_payment_cannot_be_deleted_directly(self):
        wizard = self._wizard_for('delete', reason='Duplicate')
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertTrue(self.payment.exists())

    def test_reversal_refused_in_a_locked_period(self):
        self.company.fiscalyear_lock_date = self.today - timedelta(days=10)
        eligible, message = self.offset._reversal_check('cancel')
        self.assertFalse(eligible)
        self.assertIn('locked', message)

        self._decide(self.payment, 'reverse').action_cancel()

        # Nothing was reversed, and the record says why.
        self.assertEqual(self.registration.cancel_outcome, 'kept')
        self.assertEqual(self.bill.amount_residual, 0.0)
        self.assertIn('locked', ' '.join(self.registration.message_ids.mapped('body')))

    def test_reversal_refused_after_later_reconciliation_activity(self):
        self._decide(self.payment, 'keep').action_cancel()
        self.assertEqual(self.offset._reversal_check()[0], True)

        self._register(self.credit)   # the credit remainder is paid by another registration

        eligible, message = self.offset._reversal_check()
        self.assertFalse(eligible)
        self.assertIn('reconciled again', message)
        self.assertEqual(self.offset.reversal_status, 'blocked')

    def test_ownership_cannot_be_proven_for_a_different_reconciliation(self):
        self._decide(self.payment, 'keep').action_cancel()
        partial = self.offset.partial_id
        # Same lines and amount but another partial: a hand-made reconciliation is not ours.
        lines = partial.debit_move_id | partial.credit_move_id
        partial.unlink()
        lines.reconcile()
        self.assertFalse(self.offset.partial_id)
        self.assertEqual(self.offset.reversal_status, 'removed')
        self.assertFalse(self.registration._remittance_active_offsets())

    def test_offsets_of_an_active_payment_cannot_be_reversed_on_their_own(self):
        eligible, message = self.offset._reversal_check('offsets_only')
        self.assertFalse(eligible)
        self.assertIn('still active', message)

    # ------------------------------------------------------------------
    # Wizard
    # ------------------------------------------------------------------
    def _wizard_for(self, operation, **values):
        return self.env['enterprise.remittance.cancel.wizard'].create({
            'operation': operation,
            'registration_ids': [Command.set(self.registration.ids)],
            'payment_ids': [Command.set(self.payment.ids)],
            **values,
        })

    def test_wizard_previews_eligibility(self):
        wizard = self._wizard_for('cancel', reason='x')
        self.assertEqual((wizard.eligible_count, wizard.blocked_count), (1, 0))
        self.assertTrue(wizard.can_reverse)
        self.assertEqual(wizard.allocation_ids, self.registration.allocation_ids)
        self.assertEqual(wizard.reconciliation_ids, self.offset)
        self.assertEqual(wizard.reconciliation_ids.with_context(remittance_operation='cancel').reversal_status, 'eligible')
        # The table shown in the dialog is rendered on the server with the wizard's own operation.
        self.assertIn('Can be reversed', wizard.offsets_html)
        self.assertIn(self.offset.credit_document, wizard.offsets_html)
        self.assertNotIn('still active', wizard.offsets_html)

    def test_offsets_table_explains_why_an_active_payment_cannot_have_only_its_offsets_reversed(self):
        wizard = self._wizard_for('offsets_only', reason='x')
        self.assertIn('Cannot be reversed', wizard.offsets_html)
        self.assertIn('still active', wizard.offsets_html)

    def test_offsets_table_when_there_is_nothing_to_reverse(self):
        bill = self._bill(self.vendor_b, 100.0, ref='B')
        payment = self._register(bill)
        wizard = self.env['enterprise.remittance.cancel.wizard'].create({
            'operation': 'cancel', 'registration_ids': [Command.set(payment.remittance_registration_ids.ids)],
            'payment_ids': [Command.set(payment.ids)], 'reason': 'x'})
        self.assertIn('no bill/credit offset', wizard.offsets_html)
        self.assertFalse(wizard.can_reverse)

    def test_wizard_refreshes_the_form_it_was_opened_from(self):
        action = self._wizard_for('cancel', reason='Bank rejected it').action_confirm()
        self.assertEqual(action, {'type': 'ir.actions.client', 'tag': 'soft_reload'})

    def test_wizard_keep_is_the_default_and_needs_a_reason(self):
        wizard = self._wizard_for('cancel', reason='  ')
        self.assertEqual(wizard.outcome, 'keep')
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.reason = 'Bank rejected it'
        wizard.action_confirm()
        self.assertEqual(self.payment.state, 'canceled')
        self.assertEqual(self.registration.cancel_outcome, 'kept')
        self.assertEqual(self.registration.cancel_reason, 'Bank rejected it')

    def test_wizard_reverse(self):
        self._wizard_for('cancel', outcome='reverse', reason='Bank rejected it').action_confirm()
        self.assertEqual(self.registration.cancel_outcome, 'reversed')
        self.assertEqual(self.bill.amount_residual, 1461.32)

    def test_wizard_delete_returns_to_the_payment_list(self):
        self._decide(self.payment, 'keep').action_draft()
        action = self._wizard_for('delete', reason='Duplicate').action_confirm()
        self.assertFalse(self.payment.exists())
        self.assertEqual(action['res_model'], 'account.payment')
        self.assertEqual(self.registration.state, 'deleted')

    def test_wizard_refuses_to_reverse_when_nothing_is_eligible(self):
        self.company.fiscalyear_lock_date = self.today - timedelta(days=10)
        wizard = self._wizard_for('cancel', outcome='reverse', reason='x')
        self.assertFalse(wizard.can_reverse)
        self.assertTrue(wizard.reverse_blocker)
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertEqual(self.payment.state, 'paid')

    def test_reversing_offsets_that_were_kept_earlier(self):
        self._decide(self.payment, 'keep').action_cancel()
        self.assertEqual(self.credit.amount_residual, 723.87)

        action = self.registration.action_reverse_retained_offsets()
        self.assertEqual(action['context']['default_operation'], 'offsets_only')
        wizard = self.env['enterprise.remittance.cancel.wizard'].create({
            'operation': 'offsets_only', 'registration_ids': [Command.set(self.registration.ids)],
            'reason': 'Vendor confirmed the credit is still open',
        })
        wizard.action_confirm()

        self.assertEqual(self.registration.cancel_operation, 'offsets_only')
        self.assertEqual(self.registration.cancel_outcome, 'reversed')
        self.assertEqual(self.bill.amount_residual, 1461.32)
        self.assertEqual(self.credit.amount_residual, 2185.19)

    def test_an_accounting_administrator_can_reverse_without_the_full_features_flag(self):
        """In this Odoo 19 the Administrator role does not imply 'Show Full Accounting Features'."""
        administrator = new_test_user(self.env, login='erm_admin_only', groups='base.group_user,account.group_account_manager')
        self.assertFalse(administrator.has_group('account.group_account_user'))
        wizard = self.env['enterprise.remittance.cancel.wizard'].with_user(administrator).create({
            'operation': 'cancel', 'registration_ids': [Command.set(self.registration.ids)],
            'payment_ids': [Command.set(self.payment.ids)], 'outcome': 'reverse', 'reason': 'Issued in error',
        })
        self.assertTrue(wizard.can_reverse)
        wizard.action_confirm()
        self.assertEqual(self.registration.cancel_outcome, 'reversed')
        self.assertEqual(self.registration.cancel_user_id, administrator)
        self.assertEqual(self.bill.amount_residual, 1461.32)

    def test_only_accountants_can_reverse(self):
        billing = new_test_user(self.env, login='erm_billing', groups='base.group_user,account.group_account_invoice')
        wizard = self.env['enterprise.remittance.cancel.wizard'].with_user(billing).create({
            'operation': 'cancel', 'registration_ids': [Command.set(self.registration.ids)],
            'payment_ids': [Command.set(self.payment.ids)], 'outcome': 'reverse', 'reason': 'x',
        })
        self.assertFalse(wizard.can_reverse)
        with self.assertRaises(AccessError):
            wizard.action_confirm()

        # The safe default is open to billing users, end to end through the wizard.
        wizard.outcome = 'keep'
        wizard.action_confirm()
        self.assertEqual(self.payment.state, 'canceled')
        self.assertEqual(self.registration.cancel_user_id, billing)
        self.assertEqual(self.registration.cancel_outcome, 'kept')

    # ------------------------------------------------------------------
    # Removal outside the wizard
    # ------------------------------------------------------------------
    def test_unreconciling_from_the_bill_is_stamped_in_the_trail(self):
        self.offset.partial_id.unlink()   # what the payment widget's remove button does
        self.assertFalse(self.offset.partial_id)
        self.assertEqual(self.offset.removed_via, 'external')
        self.assertEqual(self.offset.removed_by_id, self.env.user)
        self.assertTrue(self.offset.removed_on)
        self.assertEqual(self.offset.reversal_status, 'removed')
