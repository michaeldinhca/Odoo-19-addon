from datetime import timedelta

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class RemittanceCommon(AccountTestInvoicingCommon):
    """Shared helpers. Dates are relative to today so lock-date checks behave the same on any day."""

    chart_template = 'generic_coa'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.today()
        cls.bill_date = cls.today - timedelta(days=30)
        cls.vendor_a = cls.env['res.partner'].create({'name': 'Vendor A', 'email': 'vendor.a@example.com'})
        cls.vendor_b = cls.env['res.partner'].create({'name': 'Vendor B', 'email': 'vendor.b@example.com'})
        cls.expense_account = cls.company_data['default_account_expense']

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    @classmethod
    def _make_move(cls, partner, move_type, amount, ref=None, date=None, currency=None, company=None, post=True):
        company = company or cls.env.company
        vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': date or cls.bill_date,
            'date': date or cls.bill_date,
            'ref': ref,
            'invoice_line_ids': [Command.create({
                'name': ref or 'Line', 'quantity': 1, 'price_unit': amount, 'tax_ids': False,
            })],
        }
        if currency:
            vals['currency_id'] = currency.id
        move = cls.env['account.move'].with_company(company).create(vals)
        if post:
            move.action_post()
        return move

    @classmethod
    def _bill(cls, partner, amount, ref=None, **kwargs):
        return cls._make_move(partner, 'in_invoice', amount, ref=ref, **kwargs)

    @classmethod
    def _credit(cls, partner, amount, ref=None, **kwargs):
        return cls._make_move(partner, 'in_refund', amount, ref=ref, **kwargs)

    # ------------------------------------------------------------------
    # Native wizard
    # ------------------------------------------------------------------
    def _wizard(self, moves, group=None, amount=None, currency=None, **values):
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=moves.ids).create({})
        if group is not None:
            wizard.group_payment = group
        if currency is not None:
            wizard.currency_id = currency
        if amount is not None:
            wizard.amount = amount
        if values:
            wizard.write(values)
        return wizard

    def _register(self, moves, **kwargs):
        """Run the native flow exactly as the button does and return the created payments."""
        return self._wizard(moves, **kwargs)._create_payments()

    def _documents_reconciled_with_payment(self, payment):
        """Documents that have a partial reconcile against the payment entry itself (what it applied directly)."""
        lines = payment.move_id.line_ids.filtered(lambda line: line.account_type == 'liability_payable')
        partials = lines.matched_debit_ids | lines.matched_credit_ids
        return (partials.debit_move_id | partials.credit_move_id).move_id - payment.move_id

    def _registration(self, payment):
        registration = payment.remittance_registration_ids
        self.assertEqual(len(registration), 1, "Exactly one remittance record expected for %s" % payment.name)
        return registration

    def _line(self, registration, move):
        line = registration.allocation_ids.filtered(lambda alloc: alloc.move_id == move)
        self.assertEqual(len(line), 1, "Exactly one allocation line expected for %s" % move.name)
        return line

    def assertLine(self, line, *, original, due_before, applied, remaining, payment_applied=None, offset_applied=None):
        currency = line.currency_id
        for field_name, expected in (
            ('original_amount', original), ('amount_due_before', due_before),
            ('amount_applied', applied), ('amount_remaining', remaining),
            ('payment_applied', payment_applied), ('offset_applied', offset_applied),
        ):
            if expected is not None:
                self.assertAlmostEqual(
                    line[field_name], expected, places=currency.decimal_places,
                    msg="%s of %s" % (field_name, line.document_name))
