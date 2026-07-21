from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

# See test_cash_flow_forecast_report.py for why flush_all() is needed after
# posting and before querying a raw SQL-view model in the same transaction.


@tagged('post_install', '-at_install')
class TestCashFlowActualDaily(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env['account.move'])

        # This view aggregates ALL account.move.line activity for a company
        # within a date range, unlike most tests elsewhere in this module
        # which filter to a specific record id - so it isn't immune to
        # leftover entries from other manual/automated activity sitting in
        # a long-lived dev database. Use a throwaway company, guaranteed to
        # have zero pre-existing history, instead of the shared default one.
        cls.company = cls.env['res.company'].create({'name': 'Actual Daily Test Co'})
        cls.env.user.write({'company_ids': [(4, cls.company.id)]})
        cls.bank_account = cls.env['account.account'].create({
            'name': 'Actual Daily Test Bank',
            'code': 'ADB1',
            'account_type': 'asset_cash',
            'company_ids': [(6, 0, [cls.company.id])],
        })
        cls.income_account = cls.env['account.account'].create({
            'name': 'Actual Daily Test Income',
            'code': 'ADI1',
            'account_type': 'income',
            'company_ids': [(6, 0, [cls.company.id])],
        })
        cls.bank_journal = cls.env['account.journal'].create({
            'name': 'Actual Daily Test Bank Journal',
            'code': 'ADBJ',
            'type': 'bank',
            'company_id': cls.company.id,
            'default_account_id': cls.bank_account.id,
        })

    def _post_bank_entry(self, date, amount):
        """Posts a direct entry crediting/debiting the bank account by
        `amount` (positive = incoming, negative = outgoing) on `date`,
        under the isolated test company set up in setUpClass.
        """
        debit_account, credit_account = (
            (self.bank_account, self.income_account) if amount >= 0
            else (self.income_account, self.bank_account)
        )
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': date,
            'journal_id': self.bank_journal.id,
            'company_id': self.company.id,
            'line_ids': [
                (0, 0, {'account_id': debit_account.id, 'debit': abs(amount), 'credit': 0.0, 'name': 'Test'}),
                (0, 0, {'account_id': credit_account.id, 'debit': 0.0, 'credit': abs(amount), 'name': 'Test'}),
            ],
        })
        move.action_post()
        return move

    def test_single_day_entry_produces_one_row(self):
        self._post_bank_entry(self.today, 500.0)
        self.env.flush_all()

        rows = self.env['cash.flow.actual.daily'].search([
            ('company_id', '=', self.company.id),
            ('activity_date', '=', self.today),
        ])
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows.amount_in, 500.0, places=2)
        self.assertAlmostEqual(rows.amount_out, 0.0, places=2)
        self.assertAlmostEqual(rows.net_amount, 500.0, places=2)

    def test_multiple_entries_same_day_aggregate(self):
        day = self.today - relativedelta(days=10)
        self._post_bank_entry(day, 300.0)
        self._post_bank_entry(day, -120.0)
        self.env.flush_all()

        row = self.env['cash.flow.actual.daily'].search([
            ('company_id', '=', self.company.id),
            ('activity_date', '=', day),
        ])
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row.amount_in, 300.0, places=2)
        self.assertAlmostEqual(row.amount_out, 120.0, places=2)
        self.assertAlmostEqual(row.net_amount, 180.0, places=2)

    def test_entries_on_different_days_produce_separate_rows(self):
        day1 = self.today - relativedelta(days=20)
        day2 = self.today - relativedelta(days=21)
        self._post_bank_entry(day1, 100.0)
        self._post_bank_entry(day2, 200.0)
        self.env.flush_all()

        rows = self.env['cash.flow.actual.daily'].search([
            ('company_id', '=', self.company.id),
            ('activity_date', 'in', [day1, day2]),
        ])
        self.assertEqual(len(rows), 2)
        by_date = {r.activity_date: r.amount_in for r in rows}
        self.assertAlmostEqual(by_date[day1], 100.0, places=2)
        self.assertAlmostEqual(by_date[day2], 200.0, places=2)
