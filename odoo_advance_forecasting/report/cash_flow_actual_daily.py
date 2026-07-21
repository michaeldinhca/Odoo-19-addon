from odoo import fields, models, tools


class CashFlowActualDaily(models.Model):
    """Read-only SQL-view report of REALIZED (historical/current) cash
    movement, one row per (company, date). This is the ground-truth data
    layer for predictive forecasting methods - e.g. ``cash.flow.forecast
    .scenario._run_historical_trend()`` aggregates this daily data up to
    weekly buckets to compute a trailing average. Mirrors
    ``cash.flow.forecast.report``'s role as a shared, reusable view rather
    than baking the same query into every consumer.

    Uses the same ``account_type = 'asset_cash'`` filter already proven
    correct for the opening balance in ``cash.flow.forecast.report`` (see
    that model's docstring for why journal-based filtering was wrong) - this
    is reused ground truth, not a new assumption.

    Row ids are synthesized as ``company_id * 100000 + (date - 2020-01-01)``
    (days since an arbitrary epoch) to keep one unique row per company+date
    without a separate sequence; safe for roughly the next 270 years before
    the day-count component could exceed the multiplier.

    Known v1 limitation: a one-off large entry (e.g. an opening bank
    statement "first synchronization" balance) isn't distinguished from real
    recurring activity here, and could skew whichever week's trailing
    average it falls into - no filtering heuristic for this in v1.
    """

    _name = 'cash.flow.actual.daily'
    _description = 'Cash Flow Actual (Daily)'
    _auto = False
    _order = 'activity_date asc'

    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    activity_date = fields.Date(string='Date', readonly=True)
    amount_in = fields.Monetary(string='Incoming', currency_field='currency_id', readonly=True)
    amount_out = fields.Monetary(string='Outgoing', currency_field='currency_id', readonly=True)
    net_amount = fields.Monetary(string='Net Amount', currency_field='currency_id', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT
                    (aml.company_id::bigint * 100000 + (aml.date - DATE '2020-01-01')) AS id,
                    aml.company_id AS company_id,
                    c.currency_id AS currency_id,
                    aml.date AS activity_date,
                    SUM(CASE WHEN aml.balance > 0 THEN aml.balance ELSE 0 END) AS amount_in,
                    SUM(CASE WHEN aml.balance < 0 THEN -aml.balance ELSE 0 END) AS amount_out,
                    SUM(aml.balance) AS net_amount
                FROM account_move_line aml
                JOIN account_account aa ON aa.id = aml.account_id
                JOIN account_move am ON am.id = aml.move_id
                JOIN res_company c ON c.id = aml.company_id
                WHERE aa.account_type = 'asset_cash' AND am.state = 'posted'
                GROUP BY aml.company_id, c.currency_id, aml.date
            )
        """ % {'table': self._table})
