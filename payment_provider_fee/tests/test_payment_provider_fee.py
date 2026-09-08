from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestPaymentProviderFee(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['payment.provider'].create({
            'name': 'Test Provider',
            'company_id': cls.company_data['company'].id,
            'provider_fee_enabled': True,
            'provider_fee_fixed_amount': 5.0,
            'provider_fee_percentage': 3.0,
            'provider_fee_amount_min': 2.0,
            'provider_fee_amount_max': 100.0,
            'provider_fee_order_threshold': 0.0,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'type': 'service',
            'lst_price': 100.0,
            # No taxes, so amount_total stays exactly equal to price_unit in these tests --
            # the company's default sale tax would otherwise get auto-applied here.
            'taxes_id': [(6, 0, [])],
        })

    def _create_order(self, amount=100.0):
        # AccountTestInvoicingCommon's test user has accounting rights but not the Sales
        # group, which sale.order.create() requires -- sudo() here since these tests are about
        # payment_provider_fee's business logic, not sale.order's own ACLs.
        return self.env['sale.order'].sudo().create({
            'partner_id': self.partner_a.id,
            'company_id': self.company_data['company'].id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': amount,
            })],
        })

    def _create_invoice(self, amount=100.0):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': amount,
            })],
        })
        move.action_post()
        return move

    # --- Fee computation ---------------------------------------------------

    def test_compute_provider_fee_fixed_and_percentage(self):
        # 5 fixed + 3% of 100 = 8.0, within [2, 100] caps.
        fee = self.provider._compute_provider_fee(100.0, self.company_data['currency'])
        self.assertEqual(fee, 8.0)

    def test_compute_provider_fee_minimum_floor(self):
        # 5 fixed + 3% of 10 = 5.3 -> below configured min? no, min is 2, so untouched.
        # Use a provider with a higher floor to actually exercise the cap.
        provider = self.provider.copy({'provider_fee_amount_min': 10.0})
        fee = provider._compute_provider_fee(10.0, self.company_data['currency'])
        self.assertEqual(fee, 10.0)

    def test_compute_provider_fee_maximum_ceiling(self):
        provider = self.provider.copy({'provider_fee_amount_max': 20.0})
        fee = provider._compute_provider_fee(10000.0, self.company_data['currency'])
        self.assertEqual(fee, 20.0)

    def test_compute_provider_fee_order_threshold(self):
        provider = self.provider.copy({'provider_fee_order_threshold': 50.0})
        self.assertEqual(provider._compute_provider_fee(49.0, self.company_data['currency']), 0.0)
        self.assertGreater(provider._compute_provider_fee(50.0, self.company_data['currency']), 0.0)

    def test_compute_provider_fee_disabled(self):
        provider = self.provider.copy({'provider_fee_enabled': False})
        self.assertEqual(provider._compute_provider_fee(100.0, self.company_data['currency']), 0.0)

    # --- Sale order fee line ------------------------------------------------

    def test_sale_order_apply_fee_adds_line(self):
        order = self._create_order(100.0)
        base_total = order.amount_total
        new_total = order._apply_payment_provider_fee(self.provider)
        fee_lines = order._get_payment_provider_fee_lines()
        self.assertEqual(len(fee_lines), 1)
        self.assertEqual(new_total, base_total + 8.0)

    def test_sale_order_apply_fee_replaces_previous_line(self):
        order = self._create_order(100.0)
        order._apply_payment_provider_fee(self.provider)
        other_provider = self.provider.copy({
            'provider_fee_fixed_amount': 1.0,
            'provider_fee_percentage': 0.0,
            'provider_fee_amount_min': 0.0,
            'provider_fee_amount_max': 0.0,
        })
        order._apply_payment_provider_fee(other_provider)
        fee_lines = order._get_payment_provider_fee_lines()
        self.assertEqual(len(fee_lines), 1)
        self.assertEqual(fee_lines.price_unit, 1.0)

    def test_sale_order_apply_fee_false_removes_line(self):
        order = self._create_order(100.0)
        base_total = order.amount_total
        order._apply_payment_provider_fee(self.provider)
        final_total = order._apply_payment_provider_fee(False)
        self.assertFalse(order._get_payment_provider_fee_lines())
        self.assertEqual(final_total, base_total)

    def test_resolve_fee_applies_on_full_payment(self):
        order = self._create_order(100.0)
        pre_fee_total = order.amount_total
        amount = order._resolve_payment_provider_fee(self.provider, pre_fee_total)
        self.assertEqual(amount, pre_fee_total + 8.0)
        self.assertTrue(order._get_payment_provider_fee_lines())

    def test_resolve_fee_skips_partial_down_payment(self):
        order = self._create_order(100.0)
        pre_fee_total = order.amount_total
        partial_amount = pre_fee_total / 2
        amount = order._resolve_payment_provider_fee(self.provider, partial_amount)
        self.assertEqual(amount, partial_amount)
        self.assertFalse(order._get_payment_provider_fee_lines())

    def test_resolve_fee_is_idempotent_across_two_calls(self):
        order = self._create_order(100.0)
        pre_fee_total = order.amount_total
        first_amount = order._resolve_payment_provider_fee(self.provider, pre_fee_total)
        second_amount = order._resolve_payment_provider_fee(self.provider, first_amount)
        self.assertEqual(first_amount, second_amount)
        self.assertEqual(len(order._get_payment_provider_fee_lines()), 1)

    # --- Invoice fee ---------------------------------------------------------

    def test_invoice_fee_on_draft_invoice_adds_line(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        base_amount = move._get_invoice_next_payment_values()['next_amount_to_pay']
        amount, linked_ids = move._resolve_payment_provider_fee(self.provider, base_amount)
        self.assertEqual(linked_ids, [move.id])
        self.assertTrue(move._get_payment_provider_fee_lines())
        self.assertEqual(amount, move.amount_total)

    def test_invoice_fee_on_posted_invoice_creates_companion(self):
        move = self._create_invoice(100.0)
        base_amount = move._get_invoice_next_payment_values()['next_amount_to_pay']
        amount, linked_ids = move._resolve_payment_provider_fee(self.provider, base_amount)
        self.assertEqual(len(linked_ids), 2)
        self.assertFalse(move._get_payment_provider_fee_lines())  # Original invoice untouched.
        fee_invoice = self.env['account.move'].browse(linked_ids[1])
        self.assertEqual(fee_invoice.payment_provider_fee_origin_invoice_id, move)
        self.assertEqual(fee_invoice.state, 'posted')
        self.assertAlmostEqual(amount, base_amount + 8.0, places=2)

    def test_invoice_fee_reuses_existing_companion_invoice(self):
        move = self._create_invoice(100.0)
        base_amount = move._get_invoice_next_payment_values()['next_amount_to_pay']
        _, first_linked_ids = move._resolve_payment_provider_fee(self.provider, base_amount)
        _, second_linked_ids = move._resolve_payment_provider_fee(self.provider, base_amount)
        self.assertEqual(first_linked_ids, second_linked_ids)
        companion_invoices = self.env['account.move'].search([
            ('payment_provider_fee_origin_invoice_id', '=', move.id),
        ])
        self.assertEqual(len(companion_invoices), 1)

    def test_invoice_fee_skipped_for_custom_partial_amount(self):
        move = self._create_invoice(100.0)
        base_amount = move._get_invoice_next_payment_values()['next_amount_to_pay']
        custom_amount = base_amount / 2
        amount, linked_ids = move._resolve_payment_provider_fee(self.provider, custom_amount)
        self.assertEqual(amount, custom_amount)
        self.assertEqual(linked_ids, [move.id])
