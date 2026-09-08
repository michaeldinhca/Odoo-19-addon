from dateutil.relativedelta import relativedelta

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.fields import Date
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestLateFeeConfirm(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.late_fee_product = cls.env['product.product'].create({
            'name': 'Late Fee',
            'type': 'service',
            'lst_price': 0.0,
            'taxes_id': [(6, 0, [])],
        })
        cls.late_fee_model = cls.env['late.fee.model'].create({
            'name': 'Test Fixed Fee',
            'company_id': cls.company_data['company'].id,
            'is_company_default': True,
            'computation_type': 'fixed',
            'fixed_amount': 25.0,
            'interval_type': 'month',
            'recurrence': 'once',
            'late_fee_product_id': cls.late_fee_product.id,
        })
        cls.payment_term_immediate = cls.env.ref(
            'account.account_payment_term_immediate')

    def _create_overdue_invoice(self, price_unit=500.0, days_overdue=10):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': Date.today() - relativedelta(days=days_overdue),
            'invoice_payment_term_id': self.payment_term_immediate.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test product', 'quantity': 1, 'price_unit': price_unit,
            })],
        })
        move.action_post()
        self.env['account.late.fee']._cron_generate_late_fees()
        return move, self.env['account.late.fee'].search([('move_id', '=', move.id)])

    def test_confirm_locks_amount_and_sends_summary_no_invoice_yet(self):
        move, fee = self._create_overdue_invoice()
        self.assertEqual(fee.state, 'draft')

        fee.action_confirm()

        self.assertEqual(fee.state, 'confirmed')
        self.assertTrue(fee.confirmed_date)
        self.assertFalse(fee.fee_move_id, 'Confirming must not create an invoice')
        self.assertTrue(fee.mail_sent, 'A summary email must go out on confirm')
        self.assertEqual(move.late_fee_status, 'confirmed')

    def test_confirm_batch_same_customer_sends_one_summary_email(self):
        _move1, fee1 = self._create_overdue_invoice(price_unit=100.0)
        _move2, fee2 = self._create_overdue_invoice(price_unit=200.0)
        fees = fee1 | fee2

        # Both belong to partner_a; confirming together must not blow up
        # and must mark both as confirmed with a summary sent.
        fees.action_confirm()

        self.assertTrue(all(f.state == 'confirmed' for f in fees))
        self.assertTrue(all(f.mail_sent for f in fees))

    def test_consolidated_invoice_creates_one_invoice_for_multiple_fees(self):
        _move1, fee1 = self._create_overdue_invoice(price_unit=100.0)
        _move2, fee2 = self._create_overdue_invoice(price_unit=200.0)
        fees = fee1 | fee2
        fees.action_confirm()

        fees.action_create_consolidated_invoice()

        self.assertTrue(all(f.state == 'invoiced' for f in fees))
        self.assertTrue(all(f.invoiced_date for f in fees))
        invoices = fees.mapped('fee_move_id')
        self.assertEqual(len(invoices), 1, 'Both fees must land on the SAME invoice')
        invoice = invoices
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertAlmostEqual(invoice.amount_total, 50.0, places=2)  # 25 + 25
        self.assertTrue(all(f.mail_sent for f in fees))

    def test_consolidated_invoice_rejects_mixed_customers(self):
        partner_b = self.env['res.partner'].create({'name': 'Another Customer'})
        _move1, fee1 = self._create_overdue_invoice()
        move2 = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner_b.id,
            'invoice_date': Date.today() - relativedelta(days=10),
            'invoice_payment_term_id': self.payment_term_immediate.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test product', 'quantity': 1, 'price_unit': 500.0,
            })],
        })
        move2.action_post()
        self.env['account.late.fee']._cron_generate_late_fees()
        fee2 = self.env['account.late.fee'].search([('move_id', '=', move2.id)])
        fees = fee1 | fee2
        fees.action_confirm()

        with self.assertRaises(Exception):
            fees.action_create_consolidated_invoice()

    def test_waive_from_draft_leaves_no_trace(self):
        _move, fee = self._create_overdue_invoice()
        fee.action_waive()
        self.assertEqual(fee.state, 'waived')
        self.assertFalse(fee.fee_move_id)

    def test_waive_from_confirmed_still_allowed(self):
        _move, fee = self._create_overdue_invoice()
        fee.action_confirm()
        self.assertEqual(fee.state, 'confirmed')
        fee.action_waive()
        self.assertEqual(fee.state, 'waived')
        self.assertFalse(fee.fee_move_id)

    def test_edit_amount_blocked_after_confirm(self):
        _move, fee = self._create_overdue_invoice()
        fee.action_confirm()
        with self.assertRaises(Exception):
            fee.write({'fee_amount': 999.0})
