from datetime import timedelta

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import RemittanceCommon

MODELS = (
    'enterprise.remittance.registration',
    'enterprise.remittance.allocation',
    'enterprise.remittance.reconciliation',
)


@tagged('post_install', '-at_install')
class TestRemittanceSecurity(RemittanceCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_2 = cls.setup_other_company()['company']
        cls.vendor_2 = cls.env['res.partner'].create({'name': 'Vendor Two', 'company_id': False})

    def setUp(self):
        super().setUp()
        self.bill = self._bill(self.vendor_a, 1461.32, ref='BILL-1')
        self.credit = self._credit(self.vendor_a, 2185.19, ref='CN-1')
        self.payment = self._register(self.bill | self.credit, group=True)
        self.registration = self._registration(self.payment)

    def _user(self, login, groups):
        return new_test_user(self.env, login=login, groups=groups)

    def assertRefused(self, function, *args, **kwargs):
        """The operation must be refused by access rights or by the immutability guard."""
        try:
            with self.env.cr.savepoint():
                function(*args, **kwargs)
        except (AccessError, UserError):
            return
        self.fail("The operation should have been refused")

    # ------------------------------------------------------------------
    # Access rights
    # ------------------------------------------------------------------
    def test_billing_and_readonly_users_read_but_never_write(self):
        for login, group in (('erm_bill', 'account.group_account_invoice'),
                             ('erm_ro', 'account.group_account_readonly'),
                             ('erm_mgr', 'account.group_account_manager')):
            user = self._user(login, 'base.group_user,' + group)
            with self.subTest(group=group):
                for model, record in zip(MODELS, (self.registration, self.registration.allocation_ids,
                                                  self.registration.reconciliation_ids)):
                    as_user = record.with_user(user)
                    self.assertTrue(as_user.exists())
                    as_user.read(['create_date'])
                    self.assertRefused(as_user.write, {'create_date': '2020-01-01'})
                    self.assertRefused(as_user.unlink)
                    with self.assertRaises(AccessError):
                        self.env[model].with_user(user).create({})

    def test_a_plain_internal_user_has_no_access(self):
        user = self._user('erm_plain', 'base.group_user')
        for model in MODELS:
            with self.subTest(model=model), self.assertRaises(AccessError):
                self.env[model].with_user(user).search([])

    def test_debug_snapshot_is_restricted_to_advisers(self):
        billing = self._user('erm_bill2', 'base.group_user,account.group_account_invoice')
        adviser = self._user('erm_adviser', 'base.group_user,account.group_account_manager')
        with self.assertRaises(AccessError):
            self.registration.with_user(billing).debug_snapshot
        with self.assertRaises(AccessError):
            self.payment.with_user(billing).remittance_debug_snapshot
        self.assertIn('|%s|' % self.bill.id, self.registration.with_user(adviser).debug_snapshot)
        self.assertEqual(self.payment.with_user(adviser).remittance_debug_snapshot,
                         self.registration.debug_snapshot)

    def test_billing_user_registers_a_payment_end_to_end_without_direct_access_to_the_audit_tables(self):
        billing = self._user('erm_bill3', 'base.group_user,account.group_account_invoice')
        bill = self._bill(self.vendor_b, 75.0, ref='B75')
        wizard = self.env['account.payment.register'].with_user(billing).with_context(
            active_model='account.move', active_ids=bill.ids).create({})
        payment = wizard._create_payments()
        self.assertEqual(payment.remittance_registration_ids.net_amount, 75.0)
        self.assertEqual(payment.remittance_registration_ids.create_uid, billing)

    # ------------------------------------------------------------------
    # Multi-company
    # ------------------------------------------------------------------
    def _register_in_company_2(self):
        bill = self._make_move(self.vendor_2, 'in_invoice', 500.0, ref='C2-B', company=self.company_2)
        credit = self._make_move(self.vendor_2, 'in_refund', 800.0, ref='C2-C', company=self.company_2)
        wizard = self.env['account.payment.register'].with_company(self.company_2).with_context(
            active_model='account.move', active_ids=(bill | credit).ids).create({})
        wizard.group_payment = True
        payment = wizard._create_payments()
        return bill, credit, payment

    def test_records_are_isolated_by_company(self):
        _bill, _credit, payment_2 = self._register_in_company_2()
        registration_2 = self._registration(payment_2)
        self.assertEqual(registration_2.company_id, self.company_2)
        self.assertEqual(registration_2.allocation_ids.company_id, self.company_2)
        self.assertEqual(registration_2.reconciliation_ids.company_id, self.company_2)

        user_1 = new_test_user(self.env, login='erm_c1', groups='base.group_user,account.group_account_invoice',
                               company_ids=[Command.set(self.company.ids)], company_id=self.company.id)
        for model in MODELS:
            found = self.env[model].with_user(user_1).search([])
            with self.subTest(model=model):
                self.assertNotIn(self.company_2, found.company_id)
                self.assertIn(self.company, found.company_id)
        with self.assertRaises(AccessError):
            registration_2.with_user(user_1).name

        user_both = new_test_user(
            self.env, login='erm_both', groups='base.group_user,account.group_account_invoice',
            company_ids=[Command.set((self.company | self.company_2).ids)], company_id=self.company.id)
        both = self.env['enterprise.remittance.registration'].with_user(user_both).with_context(
            allowed_company_ids=(self.company | self.company_2).ids).search([])
        self.assertIn(registration_2, both)
        self.assertIn(self.registration, both)

    def test_capture_uses_the_company_of_the_payment(self):
        _bill, _credit, payment_2 = self._register_in_company_2()
        self.company_2.remittance_capture_enabled = False
        bill_3 = self._make_move(self.vendor_2, 'in_invoice', 10.0, ref='C2-3', company=self.company_2)
        wizard = self.env['account.payment.register'].with_company(self.company_2).with_context(
            active_model='account.move', active_ids=bill_3.ids).create({})
        untracked = wizard._create_payments()
        self.assertFalse(untracked.remittance_registration_ids)      # company 2 switch is off
        # Company 1 is unaffected.
        self.assertTrue(self._register(self._bill(self.vendor_b, 5.0)).remittance_registration_ids)

    def test_reversal_needs_every_involved_company_to_be_enabled(self):
        _bill, _credit, payment_2 = self._register_in_company_2()
        registration_2 = self._registration(payment_2)
        offset = registration_2.reconciliation_ids.filtered(lambda row: row.kind == 'offset')
        self.assertEqual(len(offset), 1)
        # Cancel first so the offset itself is what is being judged.
        payment_2.with_company(self.company_2).with_context(remittance_offset_decision='keep').action_cancel()

        eligible, _message = offset.with_context(allowed_company_ids=self.company_2.ids)._reversal_check()
        self.assertTrue(eligible)
        eligible, message = offset.with_context(allowed_company_ids=self.company.ids)._reversal_check()
        self.assertFalse(eligible)
        self.assertIn('company switcher', message)

    def test_lock_date_of_the_document_company_is_the_one_that_counts(self):
        _bill, _credit, payment_2 = self._register_in_company_2()
        registration_2 = self._registration(payment_2)
        offset = registration_2.reconciliation_ids.filtered(lambda row: row.kind == 'offset')
        payment_2.with_company(self.company_2).with_context(remittance_offset_decision='keep').action_cancel()
        # Locking company 1 does not affect company 2's offset...
        self.company.fiscalyear_lock_date = self.today - timedelta(days=10)
        offset = offset.with_context(allowed_company_ids=self.company_2.ids)
        self.assertTrue(offset._reversal_check()[0])
        # ...locking company 2 does.
        self.company_2.fiscalyear_lock_date = self.today - timedelta(days=10)
        eligible, message = offset._reversal_check()
        self.assertFalse(eligible)
        self.assertIn('locked', message)
