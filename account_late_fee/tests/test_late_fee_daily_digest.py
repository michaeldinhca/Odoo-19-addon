from dateutil.relativedelta import relativedelta

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.fields import Date
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestLateFeeDailyDigest(AccountTestInvoicingCommon):

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

    def _create_overdue_invoice(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': Date.today() - relativedelta(days=10),
            'invoice_payment_term_id': self.payment_term_immediate.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test product', 'quantity': 1, 'price_unit': 500.0,
            })],
        })
        move.action_post()
        self.env['account.late.fee']._cron_generate_late_fees()
        return move

    def test_digest_skips_when_no_drafts(self):
        before = self.env['mail.mail'].search_count([])
        self.env['account.late.fee']._cron_send_daily_digest()
        after = self.env['mail.mail'].search_count([])
        self.assertEqual(before, after, 'No draft fees: nothing should be queued')

    def test_digest_sends_when_drafts_exist(self):
        move = self._create_overdue_invoice()
        fee = self.env['account.late.fee'].search([('move_id', '=', move.id)])
        self.assertEqual(fee.state, 'draft')

        before = self.env['mail.mail'].search_count([])
        self.env['account.late.fee']._cron_send_daily_digest()
        after = self.env['mail.mail'].search_count([])
        self.assertGreater(after, before, 'Draft fees exist: a digest mail must be queued')

    def test_digest_html_reports_correct_count_and_total(self):
        self._create_overdue_invoice()
        self._create_overdue_invoice()
        fees = self.env['account.late.fee'].search([
            ('company_id', '=', self.company_data['company'].id),
            ('state', '=', 'draft'),
        ])
        self.assertEqual(len(fees), 2)
        html_content = fees._build_digest_html()
        self.assertIn('2', html_content)
        self.assertIn('50.00', html_content)  # 2 x 25.0 fixed fee
