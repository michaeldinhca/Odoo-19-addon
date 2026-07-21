from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

# All dates below are computed relative to fields.Date.today() rather than
# hardcoded - a hardcoded future-looking date becomes a past date once
# enough real time passes, which would silently change these invoices from
# "due later" to "overdue" (bucket_date clamped to today) and break the
# date assertions.
#
# cash.flow.forecast.report is a raw SQL view with no ORM-visible field
# dependency on account.move/sale.order/purchase.order, so Odoo's automatic
# flush-before-query doesn't know to flush them before this view is queried.
# Confirmed by testing against a live Odoo 19 instance: querying the view
# right after action_post()/action_confirm() without an explicit flush_all()
# can miss the write entirely (0 rows instead of 1). Real usage isn't
# affected - separate HTTP requests each get a fresh, already-committed
# transaction - but tests must flush explicitly.
#
# cls.product below has taxes_id cleared so all amounts in these tests are
# exactly price_unit * quantity - the demo company used to verify these
# tests has a default 6% sales tax on new products, which was silently
# inflating amounts against tests that hardcoded expected totals.


@tagged('post_install', '-at_install')
class TestCashFlowForecastReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Forecast Test Partner'})
        cls.product = cls.env['product.product'].create({
            'name': 'Forecast Test Product',
            'type': 'consu',
            'list_price': 100.0,
            'taxes_id': [(6, 0, [])],
            'supplier_taxes_id': [(6, 0, [])],
        })
        cls.today = fields.Date.context_today(cls.env['account.move'])

    def test_posted_customer_invoice_creates_incoming_row(self):
        due_date = self.today + relativedelta(days=15)
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': self.today,
            'invoice_date_due': due_date,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 500.0,
            })],
        })
        move.action_post()
        self.env.flush_all()

        row = self.env['cash.flow.forecast.report'].search([
            ('move_id', '=', move.id),
            ('source_type', '=', 'customer_invoice'),
        ])
        self.assertEqual(len(row), 1)
        self.assertEqual(row.direction, 'in')
        self.assertAlmostEqual(row.amount_in, move.amount_residual, places=2)
        self.assertEqual(row.bucket_date, due_date)

    def test_posted_vendor_bill_creates_outgoing_row(self):
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_date': self.today,
            'invoice_date_due': self.today + relativedelta(days=45),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 300.0,
            })],
        })
        move.action_post()
        self.env.flush_all()

        row = self.env['cash.flow.forecast.report'].search([
            ('move_id', '=', move.id),
            ('source_type', '=', 'vendor_bill'),
        ])
        self.assertEqual(len(row), 1)
        self.assertEqual(row.direction, 'out')
        self.assertAlmostEqual(row.amount_out, move.amount_residual, places=2)

    def test_split_payment_term_creates_one_row_per_installment(self):
        # A 30/40/30 payment term makes Odoo generate one receivable line per
        # installment, each with its own date_maturity and amount_residual.
        # The forecast must reflect that split, not collapse it onto one date.
        term = self.env['account.payment.term'].create({
            'name': '30-40-30 Test Term',
            'line_ids': [
                (0, 0, {'value': 'percent', 'value_amount': 30, 'nb_days': 10}),
                (0, 0, {'value': 'percent', 'value_amount': 40, 'nb_days': 20}),
                (0, 0, {'value': 'percent', 'value_amount': 30, 'nb_days': 30}),
            ],
        })
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': self.today,
            'invoice_payment_term_id': term.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 1000.0,
            })],
        })
        move.action_post()
        self.env.flush_all()

        rows = self.env['cash.flow.forecast.report'].search([
            ('move_id', '=', move.id),
            ('source_type', '=', 'customer_invoice'),
        ], order='bucket_date asc')
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [r.bucket_date for r in rows],
            [self.today + relativedelta(days=d) for d in (10, 20, 30)],
        )
        self.assertAlmostEqual(rows[0].amount_in, 300.0, places=2)
        self.assertAlmostEqual(rows[1].amount_in, 400.0, places=2)
        self.assertAlmostEqual(rows[2].amount_in, 300.0, places=2)
        self.assertAlmostEqual(sum(rows.mapped('amount_in')), move.amount_residual, places=2)

    def test_confirmed_sale_order_creates_incoming_row_before_invoicing(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 2,
                'price_unit': 250.0,
            })],
        })
        order.action_confirm()
        self.env.flush_all()

        row = self.env['cash.flow.forecast.report'].search([
            ('sale_order_id', '=', order.id),
        ])
        self.assertEqual(len(row), 1)
        self.assertEqual(row.direction, 'in')
        self.assertAlmostEqual(row.amount_in, order.amount_total, places=2)

    def test_sale_order_fully_invoiced_shows_no_remaining_row(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 2,
                'price_unit': 250.0,
            })],
        })
        order.action_confirm()
        self.env.flush_all()
        row = self.env['cash.flow.forecast.report'].search([('sale_order_id', '=', order.id)])
        self.assertEqual(len(row), 1, "order should appear before any invoice exists")

        invoices = order._create_invoices()
        invoices.action_post()
        self.env.flush_all()

        row_after = self.env['cash.flow.forecast.report'].search([('sale_order_id', '=', order.id)])
        self.assertFalse(row_after, "order must show no remaining-amount row once fully invoiced (remaining <= 0), to avoid double-counting with the invoice's own row")
        invoice_row = self.env['cash.flow.forecast.report'].search([('move_id', 'in', invoices.ids)])
        self.assertEqual(len(invoice_row), 1)

    def test_sale_order_partially_invoiced_shows_remaining_amount(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 10,
                'price_unit': 100.0,
            })],
        })
        order.action_confirm()
        invoice = order._create_invoices()
        # Simulate a partial invoice (e.g. partial delivery) by reducing the
        # draft invoice's quantity before posting - only 3 of 10 units.
        invoice.invoice_line_ids.quantity = 3
        invoice.invoice_date = self.today
        invoice.action_post()
        self.env.flush_all()

        row = self.env['cash.flow.forecast.report'].search([('sale_order_id', '=', order.id)])
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row.amount_in, 700.0, places=2)  # 1000 - 300 invoiced
        self.assertAlmostEqual(row.already_invoiced_amount, 300.0, places=2)

        invoice_row = self.env['cash.flow.forecast.report'].search([('move_id', '=', invoice.id)])
        self.assertEqual(len(invoice_row), 1)
        self.assertAlmostEqual(invoice_row.amount_in, 300.0, places=2)
        # Total exposure across both rows must equal the full order total.
        self.assertAlmostEqual(row.amount_in + invoice_row.amount_in, order.amount_total, places=2)

    def test_down_payment_invoice_leaves_correct_remaining_amount(self):
        # Uses the real sale.advance.payment.inv wizard, not a hand-rolled
        # approximation - a down payment invoice is linked via a synthetic
        # order line (is_downpayment=True) that never moves the REAL
        # product line's qty_invoiced, which is exactly why a quantity-based
        # "remaining" calculation double-counted the down payment amount in
        # the original bug report. This test would have caught that bug.
        term = self.env['account.payment.term'].create({
            'name': 'Down Payment Test 30-40-30',
            'line_ids': [
                (0, 0, {'value': 'percent', 'value_amount': 30, 'nb_days': 10}),
                (0, 0, {'value': 'percent', 'value_amount': 40, 'nb_days': 20}),
                (0, 0, {'value': 'percent', 'value_amount': 30, 'nb_days': 30}),
            ],
        })
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'payment_term_id': term.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 100,
                'price_unit': 100.0,
            })],
        })
        order.action_confirm()
        self.assertAlmostEqual(order.amount_total, 10000.0, places=2)

        wizard = self.env['sale.advance.payment.inv'].with_context(
            active_ids=order.ids, active_model='sale.order',
        ).create({
            'advance_payment_method': 'percentage',
            'amount': 10.0,
        })
        wizard.create_invoices()
        down_payment_invoice = order.invoice_ids
        down_payment_invoice.invoice_date = self.today
        down_payment_invoice.action_post()
        self.env.flush_all()

        self.assertAlmostEqual(down_payment_invoice.amount_total, 1000.0, places=2)

        so_row = self.env['cash.flow.forecast.report'].search([('sale_order_id', '=', order.id)])
        self.assertEqual(len(so_row), 1, "exactly one remaining-amount row, not zero (old bug) and not still the full order")
        self.assertAlmostEqual(so_row.amount_in, 9000.0, places=2)
        self.assertAlmostEqual(so_row.already_invoiced_amount, 1000.0, places=2)

        dp_rows = self.env['cash.flow.forecast.report'].search([('move_id', '=', down_payment_invoice.id)])
        self.assertAlmostEqual(sum(dp_rows.mapped('amount_in')), 1000.0, places=2)

        # Total exposure (remaining order + down payment invoice) must be
        # exactly the order total - the double-counting bug would have made
        # this 11000 (order still showing full 10000 + the 1000 invoice).
        all_rows_for_order = self.env['cash.flow.forecast.report'].search([
            ('company_id', '=', order.company_id.id),
        ]).filtered(lambda r: r.sale_order_id == order or r.move_id == down_payment_invoice)
        self.assertAlmostEqual(sum(all_rows_for_order.mapped('amount_in')), 10000.0, places=2)

    def test_purchase_order_fully_billed_shows_no_remaining_row(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 2,
                'price_unit': 250.0,
            })],
        })
        order.button_confirm()
        self.env.flush_all()
        row = self.env['cash.flow.forecast.report'].search([('purchase_order_id', '=', order.id)])
        self.assertEqual(len(row), 1, "order should appear before any bill exists")

        order.action_create_invoice()
        bill = self.env['account.move'].search([('invoice_origin', '=', order.name)], limit=1)
        # This company's default bill-control policy invoices on received
        # quantity (0 by default, nothing received) rather than ordered
        # quantity - set the full quantity explicitly to simulate "fully
        # billed" regardless of that policy.
        bill.invoice_line_ids.quantity = 2
        bill.invoice_date = self.today
        bill.action_post()
        self.env.flush_all()

        row_after = self.env['cash.flow.forecast.report'].search([('purchase_order_id', '=', order.id)])
        self.assertFalse(row_after, "order must show no remaining-amount row once fully billed (remaining <= 0), to avoid double-counting with the bill's own row")

    def test_purchase_order_partially_billed_shows_remaining_amount(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 10,
                'price_unit': 100.0,
            })],
        })
        order.button_confirm()
        order.action_create_invoice()
        bill = self.env['account.move'].search([('invoice_origin', '=', order.name)], limit=1)
        bill.invoice_line_ids.quantity = 4
        bill.invoice_date = self.today
        bill.action_post()
        self.env.flush_all()

        row = self.env['cash.flow.forecast.report'].search([('purchase_order_id', '=', order.id)])
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row.amount_out, 600.0, places=2)  # 1000 - 400 billed
        self.assertAlmostEqual(row.already_invoiced_amount, 400.0, places=2)

        bill_row = self.env['cash.flow.forecast.report'].search([('move_id', '=', bill.id)])
        self.assertEqual(len(bill_row), 1)
        self.assertAlmostEqual(bill_row.amount_out, 400.0, places=2)
        self.assertAlmostEqual(row.amount_out + bill_row.amount_out, order.amount_total, places=2)

    def test_sale_order_with_payment_term_splits_into_installments(self):
        term = self.env['account.payment.term'].create({
            'name': 'SO 30-40-30 Test Term',
            'line_ids': [
                (0, 0, {'value': 'percent', 'value_amount': 30, 'nb_days': 10}),
                (0, 0, {'value': 'percent', 'value_amount': 40, 'nb_days': 20}),
                (0, 0, {'value': 'percent', 'value_amount': 30, 'nb_days': 30}),
            ],
        })
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'payment_term_id': term.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': 1000.0,
            })],
        })
        order.action_confirm()
        self.env.flush_all()

        rows = self.env['cash.flow.forecast.report'].search([
            ('sale_order_id', '=', order.id),
        ], order='bucket_date asc')
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [r.bucket_date for r in rows],
            [self.today + relativedelta(days=d) for d in (10, 20, 30)],
        )
        self.assertAlmostEqual(rows[0].amount_in, 300.0, places=2)
        self.assertAlmostEqual(rows[1].amount_in, 400.0, places=2)
        self.assertAlmostEqual(rows[2].amount_in, 300.0, places=2)

    def test_purchase_order_with_payment_term_anchors_on_planned_date(self):
        term = self.env['account.payment.term'].create({
            'name': 'PO Net 30 Test Term',
            'line_ids': [
                (0, 0, {'value': 'percent', 'value_amount': 100, 'nb_days': 30}),
            ],
        })
        planned_date = self.today + relativedelta(days=5)
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'payment_term_id': term.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 1,
                'price_unit': 800.0,
                'date_planned': planned_date,
            })],
        })
        order.button_confirm()
        self.env.flush_all()

        row = self.env['cash.flow.forecast.report'].search([('purchase_order_id', '=', order.id)])
        self.assertEqual(len(row), 1)
        # Anchored on planned_date (expected delivery), not date_order.
        self.assertEqual(row.bucket_date, planned_date + relativedelta(days=30))
        self.assertAlmostEqual(row.amount_out, 800.0, places=2)

    def test_running_balance_accumulates_in_date_order(self):
        move_early = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': self.today,
            'invoice_date_due': self.today + relativedelta(days=10),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        move_early.action_post()

        move_later = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': self.today,
            'invoice_date_due': self.today + relativedelta(days=20),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 200.0,
            })],
        })
        move_later.action_post()
        self.env.flush_all()

        rows = self.env['cash.flow.forecast.report'].search([
            ('company_id', '=', self.env.company.id),
        ], order='bucket_date asc, id asc')
        balances = {r.move_id.id: r.running_balance for r in rows if r.move_id}
        self.assertLess(
            list(balances.values()).index(balances[move_early.id]),
            list(balances.values()).index(balances[move_later.id]),
        )
