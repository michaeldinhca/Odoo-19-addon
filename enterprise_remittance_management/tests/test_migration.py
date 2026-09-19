from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.enterprise_remittance_management.wizard.remittance_migration_wizard import (
    RemittanceMigrationWizard,
    parse_legacy_snapshot,
)

from .common import RemittanceCommon


@tagged('post_install', '-at_install')
class TestLegacySnapshotParser(RemittanceCommon):

    def test_documented_format(self):
        entries, errors = parse_legacy_snapshot("5026|37309|80.08\n5018|36444|-2185.19")
        self.assertEqual([(e['vendor_id'], e['move_id'], e['amount']) for e in entries],
                         [(5026, 37309, 80.08), (5018, 36444, -2185.19)])
        self.assertFalse(errors)

    def test_separators_and_blank_lines(self):
        entries, errors = parse_legacy_snapshot("\n1|2|3.5;4|5|6.25\r\n\n7|8|-9, 10|11|12\n")
        self.assertEqual([e['move_id'] for e in entries], [2, 5, 8, 11])
        self.assertFalse(errors)

    def test_malformed_rows_are_reported_never_repaired(self):
        text = "\n".join([
            "5026|37309|80.08",     # good
            "not a row",            # wrong shape
            "12|x|3",               # non numeric
            "0|5|1",                # non positive id
            "5026|37309|1.00",      # duplicate document
            "7|8",                  # missing amount
            "9|10|1|2",             # too many values
        ])
        entries, errors = parse_legacy_snapshot(text)
        self.assertEqual([e['move_id'] for e in entries], [37309])
        self.assertEqual([position for position, _raw, _reason in errors], [2, 3, 4, 5, 6, 7])
        self.assertIn('appears more than once', errors[3][2])

    def test_empty_input(self):
        self.assertEqual(parse_legacy_snapshot(False), ([], []))
        self.assertEqual(parse_legacy_snapshot(""), ([], []))


@tagged('post_install', '-at_install')
class TestLegacyMigration(RemittanceCommon):

    def setUp(self):
        super().setUp()
        # Legacy payments are the ones created before the addon existed: no snapshot.
        self.company.remittance_capture_enabled = False
        self.bill_1 = self._bill(self.vendor_a, 100.0, ref='B1')
        self.bill_2 = self._bill(self.vendor_a, 50.0, ref='B2')
        self.credit = self._credit(self.vendor_a, 30.0, ref='C1')
        self.payment = self._register(self.bill_1 | self.bill_2 | self.credit, group=True)
        self.company.remittance_capture_enabled = True
        self.assertFalse(self.payment.remittance_registration_ids)
        self.wizard = self.env['enterprise.remittance.migration.wizard'].create({})

    # ------------------------------------------------------------------
    # Injection of legacy data through the two dynamic accessors
    # ------------------------------------------------------------------
    def _line(self, move, before, applied, remaining, total=None, label=None, currency=None):
        return {
            'label': label or 'x_payment_allocation_l#%s' % move.id, 'move': move,
            'currency': currency or self.company.currency_id,
            'total': before if total is None else total, 'before': before, 'applied': applied, 'remaining': remaining,
        }

    def _clean_lines(self):
        return [
            self._line(self.bill_1, 100.0, 100.0, 0.0),
            self._line(self.bill_2, 50.0, 50.0, 0.0),
            self._line(self.credit, -30.0, -30.0, 0.0),
        ]

    def _clean_snapshot(self):
        vendor = self.vendor_a.id
        return "%s|%s|100.00\n%s|%s|50.00\n%s|%s|-30.00" % (
            vendor, self.bill_1.id, vendor, self.bill_2.id, vendor, self.credit.id)

    def _patched(self, lines, snapshot):
        payment = self.payment
        return patch.multiple(
            RemittanceMigrationWizard,
            _legacy_setup=lambda wizard: (True, []),
            _legacy_lines_by_payment=lambda wizard: {payment.id: lines},
            _legacy_snapshot_payments=lambda wizard: {payment.id: snapshot} if snapshot else {},
        )

    # ------------------------------------------------------------------
    # Nothing to migrate
    # ------------------------------------------------------------------
    def test_fresh_database_reports_nothing_to_migrate(self):
        before = self.env['enterprise.remittance.registration'].search_count([])
        self.wizard.action_migrate()
        self.assertIn('Nothing to migrate', self.wizard.report)
        self.assertIn('x_payment_allocation_l', self.wizard.report)
        self.assertEqual(self.env['enterprise.remittance.registration'].search_count([]), before)

    # ------------------------------------------------------------------
    # Clean migration
    # ------------------------------------------------------------------
    def test_dry_run_changes_nothing(self):
        with self._patched(self._clean_lines(), self._clean_snapshot()):
            self.wizard.action_scan()
        self.assertEqual((self.wizard.payment_count, self.wizard.migrated_count, self.wizard.issue_count), (1, 1, 0))
        self.assertIn('Dry run', self.wizard.report)
        self.assertFalse(self.payment.remittance_registration_ids)

    def test_clean_migration_creates_an_immutable_record_without_inventing_values(self):
        with self._patched(self._clean_lines(), self._clean_snapshot()):
            self.wizard.action_migrate()

        registration = self.payment.remittance_registration_ids
        self.assertEqual(len(registration), 1)
        self.assertEqual(registration.origin, 'migrated')
        self.assertFalse(registration.has_diagnostic, registration.diagnostic)
        self.assertEqual(registration.net_amount, 120.0)   # 100 + 50 - 30
        self.assertEqual(len(registration.allocation_ids), 3)
        credit_line = self._line_of(registration, self.credit)
        self.assertLine(credit_line, original=-30.0, due_before=-30.0, applied=-30.0, remaining=0.0)
        self.assertFalse(credit_line.split_known)                 # payment/offset split is unknown, not guessed
        self.assertEqual(credit_line.payment_applied, 0.0)
        self.assertEqual(credit_line.offset_applied, 0.0)
        self.assertEqual(credit_line.legacy_source, 'x_payment_allocation_l#%s' % self.credit.id)
        self.assertEqual(credit_line.vendor_id, self.vendor_a)
        self.assertIn('%s|%s|-30.00' % (self.vendor_a.id, self.credit.id), registration.debug_snapshot)
        # Ownership of any reconciliation cannot be proven for migrated data.
        self.assertFalse(registration.reconciliation_ids)
        self.assertFalse(registration._remittance_active_offsets())
        with self.assertRaises(Exception):
            registration.allocation_ids.write({'amount_applied': 1.0})
        # The slip now uses the migrated snapshot.
        self.assertEqual(self.payment._remittance_slip_data()['source'], 'snapshot')

    def _line_of(self, registration, move):
        return registration.allocation_ids.filtered(lambda line: line.move_id == move)

    def test_migration_is_idempotent(self):
        with self._patched(self._clean_lines(), self._clean_snapshot()):
            self.wizard.action_migrate()
            self.wizard.action_migrate()
        self.assertEqual(len(self.payment.remittance_registration_ids), 1)
        self.assertIn('already has a remittance record', self.wizard.report)
        self.assertEqual(self.wizard.migrated_count, 0)

    # ------------------------------------------------------------------
    # Malformed and ambiguous data
    # ------------------------------------------------------------------
    def test_inconsistent_line_is_reported_and_skipped(self):
        lines = self._clean_lines()
        lines[1] = self._line(self.bill_2, 50.0, 50.0, 10.0)     # 50 - 50 is not 10
        with self._patched(lines, self._clean_snapshot()):
            self.wizard.action_migrate()

        registration = self.payment.remittance_registration_ids
        self.assertEqual(registration.allocation_ids.move_id, self.bill_1 | self.credit)
        self.assertTrue(registration.has_diagnostic)
        self.assertIn('B2', registration.diagnostic)
        self.assertIn('not the remaining', self.wizard.report)
        self.assertGreaterEqual(self.wizard.issue_count, 1)

    def test_snapshot_entry_without_an_allocation_line_is_not_invented(self):
        with self._patched(self._clean_lines()[:2], self._clean_snapshot()):    # credit line missing
            self.wizard.action_migrate()

        registration = self.payment.remittance_registration_ids
        self.assertEqual(registration.allocation_ids.move_id, self.bill_1 | self.bill_2)
        self.assertIn('has no allocation line', registration.diagnostic)
        # The applied total no longer reaches the net payment and the record says so.
        self.assertIn('may be incomplete', registration.diagnostic)

    def test_snapshot_disagreeing_with_the_line_is_reported(self):
        wrong_vendor = "%s|%s|100.00" % (self.vendor_b.id, self.bill_1.id)
        wrong_amount = "%s|%s|55.00" % (self.vendor_a.id, self.bill_2.id)
        with self._patched(self._clean_lines(), "%s\n%s" % (wrong_vendor, wrong_amount)):
            self.wizard.action_migrate()

        registration = self.payment.remittance_registration_ids
        self.assertEqual(registration.allocation_ids.move_id, self.credit)
        self.assertIn('differs from the document vendor', registration.diagnostic)
        self.assertIn('differs from the balance before payment', registration.diagnostic)

    def test_malformed_snapshot_text_is_reported_but_lines_still_import(self):
        with self._patched(self._clean_lines(), self._clean_snapshot() + "\ngarbage"):
            self.wizard.action_migrate()
        registration = self.payment.remittance_registration_ids
        self.assertEqual(len(registration.allocation_ids), 3)
        self.assertIn("'garbage' ignored", registration.diagnostic)

    def test_credit_sign_convention_is_explicit(self):
        lines = self._clean_lines()
        lines[2] = self._line(self.credit, 30.0, 30.0, 0.0)      # credit stored as a positive number
        with self._patched(lines, ''):
            self.wizard.action_migrate()
        registration = self.payment.remittance_registration_ids
        self.assertNotIn(self.credit, registration.allocation_ids.move_id)
        self.assertIn('credit with positive amounts', registration.diagnostic)

    def test_positive_credits_can_be_declared_and_are_negated(self):
        lines = self._clean_lines()
        lines[2] = self._line(self.credit, 30.0, 30.0, 0.0)
        self.wizard.credits_stored_positive = True
        with self._patched(lines, ''):
            self.wizard.action_migrate()
        registration = self.payment.remittance_registration_ids
        self.assertLine(self._line_of(registration, self.credit), original=-30.0, due_before=-30.0,
                        applied=-30.0, remaining=0.0)
        self.assertFalse(registration.has_diagnostic, registration.diagnostic)

    def test_payment_without_any_reliable_line_is_skipped(self):
        with self._patched([self._line(self.bill_1, 100.0, 100.0, 5.0)], ''):
            self.wizard.action_migrate()
        self.assertFalse(self.payment.remittance_registration_ids)
        self.assertEqual(self.wizard.skipped_count, 1)
        self.assertIn('no reliable allocation line', self.wizard.report)

    # ------------------------------------------------------------------
    # Rights and legacy artifacts
    # ------------------------------------------------------------------
    def test_only_settings_administrators_can_migrate(self):
        manager = new_test_user(self.env, login='erm_mig_manager', groups='base.group_user,account.group_account_manager')
        wizard = self.env['enterprise.remittance.migration.wizard'].with_user(manager)
        with self.assertRaises(AccessError):
            wizard.create({})

    def test_legacy_artifacts_are_listed_and_never_disabled(self):
        server_action = self.env['ir.actions.server'].create({
            'name': 'Legacy: capture selection',
            'model_id': self.env['ir.model']._get('account.move').id,
            'state': 'code',
            'code': "records.env['account.payment.register'].create({'x_studio_move_id_list': 'x'})",
        })
        view = self.env['ir.ui.view'].create({
            'name': 'legacy.remittance.slip',
            'type': 'qweb',
            'arch_db': '<t t-name="legacy.remittance.slip"><div t-foreach="doc.x_studio_invoice_bill_lines" t-as="l"/></t>',
        })
        self.wizard.action_find_legacy_artifacts()

        self.assertIn('Nothing was changed', self.wizard.report)
        self.assertIn('Server action | %s' % server_action.id, self.wizard.report)
        self.assertIn('View / report template | %s' % view.id, self.wizard.report)
        self.assertTrue(server_action.exists())
        self.assertTrue(view.active)
