from dateutil.relativedelta import relativedelta

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.fields import Date
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestLateFeeComputation(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.late_fee_product = cls.env['product.product'].create({
            'name': 'Late Fee',
            'type': 'service',
            'lst_price': 0.0,
        })
        cls.late_fee_model = cls.env['late.fee.model'].create({
            'name': 'Test 5% Monthly',
            'company_id': cls.company_data['company'].id,
            'is_company_default': True,
            'computation_type': 'percentage',
            'percentage': 5.0,
            'interval_type': 'month',
            'interval_number': 1,
            'grace_period_days': 0,
            'recurrence': 'once',
            'late_fee_product_id': cls.late_fee_product.id,
        })
        cls.payment_term_3x = cls.env['account.payment.term'].create({
            'name': '3 Installments 15/30/45',
            'line_ids': [
                (0, 0, {'value': 'percent', 'value_amount': 30.0, 'nb_days': 15}),
                (0, 0, {'value': 'percent', 'value_amount': 30.0, 'nb_days': 30}),
                (0, 0, {'value': 'percent', 'value_amount': 40.0, 'nb_days': 45}),
            ],
        })

    def _create_invoice(self, invoice_date, payment_term):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': invoice_date,
            'invoice_payment_term_id': payment_term.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test product',
                'quantity': 1,
                'price_unit': 1000.0,
            })],
        })
        move.action_post()
        return move

    def test_only_overdue_installment_is_charged(self):
        # 20 days old: the +15-day installment is overdue, the +30-day and
        # +45-day ones are not due yet.
        invoice_date = Date.today() - relativedelta(days=20)
        move = self._create_invoice(invoice_date, self.payment_term_3x)
        term_lines = move.line_ids.filtered(
            lambda l: l.display_type == 'payment_term'
        ).sorted('date_maturity')
        self.assertEqual(len(term_lines), 3)

        self.env['account.late.fee']._cron_generate_late_fees()

        fees = self.env['account.late.fee'].search([('move_id', '=', move.id)])
        self.assertEqual(
            len(fees), 1,
            'Only the overdue installment should get a fee, never the '
            'other installments that are not due yet')
        self.assertEqual(fees.invoice_line_id, term_lines[0])
        self.assertAlmostEqual(fees.overdue_amount, 300.0, places=2)
        self.assertAlmostEqual(fees.fee_amount, 15.0, places=2)
        self.assertEqual(fees.state, 'draft')

    def test_cron_is_idempotent(self):
        invoice_date = Date.today() - relativedelta(days=20)
        move = self._create_invoice(invoice_date, self.payment_term_3x)

        self.env['account.late.fee']._cron_generate_late_fees()
        self.env['account.late.fee']._cron_generate_late_fees()

        fees = self.env['account.late.fee'].search([('move_id', '=', move.id)])
        self.assertEqual(
            len(fees), 1, 'Re-running the cron must not duplicate fees')

    def test_partner_exemption_blocks_fee(self):
        self.partner_a.late_fee_exempt = True
        invoice_date = Date.today() - relativedelta(days=20)
        move = self._create_invoice(invoice_date, self.payment_term_3x)

        self.env['account.late.fee']._cron_generate_late_fees()

        fees = self.env['account.late.fee'].search([('move_id', '=', move.id)])
        self.assertFalse(fees, 'An exempt partner must never be charged')
