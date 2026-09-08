from dateutil.relativedelta import relativedelta

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.fields import Date, Datetime
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestLateFeeCronRecurrence(AccountTestInvoicingCommon):
    """Recurring-model period math and max_occurrences cap enforcement.

    These are tested against explicit `today` values / pre-seeded history
    rather than by repeatedly invoking the cron on the same calendar day,
    since the cron is only meant to advance by one period per real day
    (driven by ir.cron's daily schedule) and re-running it without time
    actually passing is a separate idempotency concern, covered in
    test_late_fee_computation.py.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.late_fee_product = cls.env['product.product'].create({
            'name': 'Late Fee', 'type': 'service', 'lst_price': 0.0,
        })
        cls.recurring_model = cls.env['late.fee.model'].create({
            'name': 'Test Recurring Monthly',
            'company_id': cls.company_data['company'].id,
            'is_company_default': True,
            'computation_type': 'fixed',
            'fixed_amount': 10.0,
            'interval_type': 'month',
            'interval_number': 1,
            'grace_period_days': 0,
            'recurrence': 'recurring',
            'max_occurrences': 3,
            'application_mode': 'new_invoice',
            'late_fee_product_id': cls.late_fee_product.id,
        })
        cls.payment_term_immediate = cls.env.ref(
            'account.account_payment_term_immediate')
        cls.move = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_a.id,
            'invoice_date': Date.today() - relativedelta(days=1),
            'invoice_payment_term_id': cls.payment_term_immediate.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test product', 'quantity': 1, 'price_unit': 100.0,
            })],
        })
        cls.move.action_post()
        cls.term_line = cls.move.line_ids.filtered(
            lambda l: l.display_type == 'payment_term')

    def test_period_index_math(self):
        # _compute_period_index counts how many period boundaries
        # (due_date+grace, then every interval) have been crossed by
        # `today`, inclusive of the first one -- i.e. period 1 becomes due
        # immediately once the installment is at all overdue (this is what
        # lets a `once` model charge right away rather than waiting a full
        # extra period), and each additional full interval elapsed after
        # that adds one more.
        LateFee = self.env['account.late.fee']
        due_date = Date.today()
        self.assertEqual(
            LateFee._compute_period_index(
                due_date, self.recurring_model, due_date - relativedelta(days=1)),
            0, 'Due date not reached yet: no period elapsed')
        self.assertEqual(
            LateFee._compute_period_index(
                due_date, self.recurring_model, due_date + relativedelta(days=1)),
            1, 'Just overdue: first period is due immediately once eligible')
        self.assertEqual(
            LateFee._compute_period_index(
                due_date, self.recurring_model,
                due_date + relativedelta(months=3, days=1)),
            4)

    def test_recurring_respects_cap_against_existing_history(self):
        LateFee = self.env['account.late.fee']
        # Simulate 2 periods already charged and confirmed in the past.
        for period in (1, 2):
            LateFee.create({
                'invoice_line_id': self.term_line.id,
                'late_fee_model_id': self.recurring_model.id,
                'period_index': period,
                'computation_date': Date.today(),
                'overdue_amount': 100.0,
                'overdue_days': 30 * period,
                'computation_type': 'fixed',
                'fixed_amount_applied': 10.0,
                'interval_type': 'month',
                'application_mode': 'new_invoice',
                'fee_amount': 10.0,
                'state': 'confirmed',
                'confirmed_date': Datetime.now(),
            })

        far_future = Date.today() + relativedelta(months=5)
        LateFee._generate_for_line(self.term_line, self.recurring_model, far_future)

        fees = LateFee.search([('invoice_line_id', '=', self.term_line.id)])
        self.assertEqual(
            len(fees), 3, 'Must stop generating once max_occurrences is reached')
        self.assertEqual(sorted(fees.mapped('period_index')), [1, 2, 3])

        # Running it again (still in the "future") must not create a 4th.
        LateFee._generate_for_line(self.term_line, self.recurring_model, far_future)
        fees = LateFee.search([('invoice_line_id', '=', self.term_line.id)])
        self.assertEqual(len(fees), 3)

    def test_once_only_charges_a_single_period(self):
        self.recurring_model.write({'recurrence': 'once'})
        LateFee = self.env['account.late.fee']
        far_future = Date.today() + relativedelta(months=5)

        LateFee._generate_for_line(self.term_line, self.recurring_model, far_future)
        LateFee._generate_for_line(self.term_line, self.recurring_model, far_future)

        fees = LateFee.search([('invoice_line_id', '=', self.term_line.id)])
        self.assertEqual(len(fees), 1)
        self.assertEqual(fees.period_index, 1)
