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
            'application_mode': 'new_invoice',
            'late_fee_product_id': cls.late_fee_product.id,
        })
        cls.payment_term_immediate = cls.env.ref(
            'account.account_payment_term_immediate')
        cls.move = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_a.id,
            'invoice_date': Date.today() - relativedelta(days=10),
            'invoice_payment_term_id': cls.payment_term_immediate.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test product', 'quantity': 1, 'price_unit': 500.0,
            })],
        })
        cls.move.action_post()
        cls.env['account.late.fee']._cron_generate_late_fees()
        cls.fee = cls.env['account.late.fee'].search(
            [('move_id', '=', cls.move.id)])

    def test_confirm_creates_new_invoice(self):
        self.assertEqual(self.fee.state, 'draft')
        self.fee.action_confirm()
        self.assertEqual(self.fee.state, 'confirmed')
        self.assertTrue(self.fee.fee_move_id)
        self.assertEqual(self.fee.fee_move_id.state, 'posted')
        self.assertEqual(self.fee.fee_move_id.invoice_origin, self.move.name)
        self.assertAlmostEqual(self.fee.fee_move_id.amount_total, 25.0, places=2)
        self.assertEqual(self.move.late_fee_status, 'applied')
        self.assertTrue(self.fee.mail_sent)

    def test_email_toggle_off_skips_send(self):
        self.late_fee_model.send_notification_email = False
        self.fee.action_confirm()
        self.assertEqual(self.fee.state, 'confirmed')
        self.assertTrue(self.fee.fee_move_id, 'The fee itself must still apply')
        self.assertFalse(self.fee.mail_sent, 'No email should be sent when disabled')

    def test_waive_leaves_no_trace(self):
        self.fee.action_waive()
        self.assertEqual(self.fee.state, 'waived')
        self.assertFalse(self.fee.fee_move_id)

    def test_edit_amount_blocked_after_confirm(self):
        self.fee.action_confirm()
        with self.assertRaises(Exception):
            self.fee.write({'fee_amount': 999.0})
