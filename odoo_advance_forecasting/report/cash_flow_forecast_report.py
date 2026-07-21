from odoo import fields, models, tools


class CashFlowForecastReport(models.Model):
    """Read-only SQL-view report projecting a running cash balance forward in
    time from confirmed documents only (posted invoices/bills, confirmed sale
    /purchase orders). Never includes drafts.

    Row ids are synthesized as ``<source_row_id> * 10 + <branch_code>``
    (0=opening balance, 1=customer invoice, 2=vendor bill, 3=sale order,
    4=purchase order) so that rows coming from different source tables can
    never collide, since each branch's driving id is a distinct table's
    primary key multiplied by 10.

    Known v1 assumptions/limitations:
    - Sale/purchase orders are only included when their currency matches the
      company currency; foreign-currency orders are excluded (see
      ``res.company.cash_forecast_default_payment_days`` help text).
    - Invoices/bills are sourced per receivable/payable *line*
      (``account.move.line`` where ``account.account_type`` is
      ``asset_receivable``/``liability_payable``, ``reconciled = False``),
      not per invoice header. This matters because a multi-installment
      payment term (e.g. 30/40/30) makes Odoo generate one receivable/
      payable line per installment, each with its own ``date_maturity`` and
      its own ``amount_residual`` — sourcing from the invoice header's
      single ``invoice_date_due``/``amount_residual`` would have dumped the
      entire residual onto one date instead of splitting it across each
      installment's real due date.
    - Sale/purchase orders use a *monetary* "already invoiced" calculation
      (``sale_order_invoiced``/``purchase_order_invoiced`` CTEs: sum of
      posted invoice/bill ``amount_total`` linked back to the order via
      ``sale_order_line_invoice_rel`` for sale orders,
      ``account_move_line.purchase_line_id`` for purchase orders,
      deduplicated per invoice), not a quantity-based ``qty_invoiced``
      ratio. This matters because a down-payment invoice is linked via a
      synthetic order line (``is_downpayment=True``) that never moves the
      real product lines' ``qty_invoiced`` - a qty-based "remaining" calc
      would keep showing the FULL order total as unforecast even after a
      down payment posts, while the down payment's own invoice row *also*
      shows up separately, double-counting it. Confirmed by actually
      creating a down payment via the real ``sale.advance.payment.inv``
      wizard against a local Odoo 19 instance and inspecting the result.
    - Sale/purchase orders with NOTHING posted-invoiced yet are split one
      row per payment-term installment, same rationale as
      customer_invoice/vendor_bill's per-installment split - a 30/40/30
      term produces 3 rows, not one row for the whole amount on a single
      crude date. Falls back to one row for the full order_total if no
      payment term is set. Sale orders anchor on ``date_order``; purchase
      orders anchor on the expected delivery date (``MIN(date_planned)``
      across lines) instead, since a purchase's payment clock realistically
      starts at receipt ("pay for what we received"), falling back to
      ``date_order`` if there's a payment term but no planned date at all.
    - Sale/purchase orders with SOME (but not all) posted-invoiced already -
      a down payment, a partial delivery invoice, or both - collapse to a
      single row for ``order_total - already_invoiced``
      (``already_invoiced_amount`` is set on that row so the Scenario layer
      can label it distinctly, e.g. "Remaining to Invoice"). Not split by
      installment: once real invoicing has started, the order's original
      payment-term schedule no longer cleanly maps to what's left - a down
      payment invoice can carry its own, unrelated payment term (confirmed
      locally: in the test scenario, the down payment invoice inherited the
      order's 30/40/30 term and got its own 3-way split, independent of the
      order's remaining schedule). Uses the same single-date fallback as
      the "nothing invoiced" branch (furthest installment day-count, then
      commitment_date/planned_date, then the default-days setting).
    - Credit notes/refunds (``move_type`` ``out_refund``/``in_refund``)
      against an order are NOT netted into ``already_invoiced`` in v1 -
      only ``out_invoice``/``in_invoice`` are counted. An order with a
      refund could show a "remaining" amount that's a bit off; not
      expected to be common, revisit if it comes up.
    - ``account.payment.term.line`` links back to its parent term via the
      ``payment_id`` column (not ``payment_term_id`` — verified against a
      live Odoo 19 install after an earlier version of this view got that
      wrong and failed on ``UndefinedColumn``).
    - ``account.move.line.amount_residual`` and ``.date_maturity`` are
      assumed to exist and behave as in standard Odoo (confirmed only
      indirectly, via the sibling repo's Aged Partner Balance report using
      ``date_maturity``/``reconciled`` at the line level) — not yet
      exercised end-to-end against this specific Odoo 19 build.

    Opening balance history: an early version summed posted move lines by
    bank/cash *journal type*, which produced $0 on real data - an
    account.payment posts to "Accounts Receivable"/"Outstanding Receipts"
    under the bank journal's journal_id, and those two lines exactly cancel
    out (neither is the real bank G/L account; the payment only actually
    reaches the bank account once reconciled against a bank statement). Now
    filters by the account's own account_type = 'asset_cash' instead, which
    is what actually identifies a real liquidity account regardless of
    which journal recorded the line. Verified directly against a local Odoo
    19 instance: a journal-based sum returned $0 for a payment that hadn't
    reached the bank account yet, and correctly returned the posted amount
    for a direct entry against the actual bank account, using the
    account_type filter.

    Performance note: this still sums every posted asset_cash move line
    ever, every time the view is queried (no caching) - it will get slower
    as a company's transaction history grows. A bank-statement-snapshot
    optimization was attempted and reverted twice (see git history around
    2026-07-18/19) due to account.bank.statement compute-chain edge cases;
    revisit only with a local Odoo instance available to verify against
    directly, not by reasoning from source alone.
    """

    _name = 'cash.flow.forecast.report'
    _description = 'Cash Flow Forecast'
    _auto = False
    _order = 'bucket_date asc, id asc'

    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    source_type = fields.Selection([
        ('opening_balance', 'Opening Balance'),
        ('customer_invoice', 'Customer Invoice'),
        ('vendor_bill', 'Vendor Bill'),
        ('sale_order', 'Sale Order'),
        ('purchase_order', 'Purchase Order'),
    ], string='Source', readonly=True)
    direction = fields.Selection([
        ('in', 'Incoming'),
        ('out', 'Outgoing'),
        ('opening', 'Opening'),
    ], string='Direction', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    move_id = fields.Many2one('account.move', string='Invoice/Bill', readonly=True)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    name = fields.Char(string='Description', readonly=True)
    already_invoiced_amount = fields.Monetary(
        string='Already Invoiced', currency_field='currency_id', readonly=True,
        help="Only set on sale_order/purchase_order rows that are partially "
             "invoiced/billed already (e.g. a down payment): the amount "
             "already posted against this order, so net_amount here is the "
             "remainder still to invoice/bill, not the whole order.",
    )
    original_due_date = fields.Date(string='Original Due Date', readonly=True)
    bucket_date = fields.Date(string='Forecast Date', readonly=True)
    is_overdue = fields.Boolean(string='Overdue', readonly=True)
    amount_in = fields.Monetary(string='Incoming', currency_field='currency_id', readonly=True)
    amount_out = fields.Monetary(string='Outgoing', currency_field='currency_id', readonly=True)
    net_amount = fields.Monetary(string='Net Amount', currency_field='currency_id', readonly=True)
    running_balance = fields.Monetary(string='Forecasted Balance', currency_field='currency_id', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %(table)s AS (
            WITH opening_balance AS (
                -- Sums posted move lines on actual liquidity (asset_cash)
                -- accounts, NOT lines merely recorded through a bank/cash
                -- *journal*. An earlier journal-based version summed to $0
                -- on real data: an account.payment posts to "Accounts
                -- Receivable" and "Outstanding Receipts" (a clearing
                -- account) under the bank journal's journal_id, and those
                -- two lines exactly cancel out - neither one is the real
                -- bank G/L account. Confirmed locally: filtering by
                -- account_type = 'asset_cash' instead of journal type gives
                -- the correct balance (verified against a direct bank
                -- account entry: journal-based sum = 0, account-type-based
                -- sum = the real posted amount). The inner subquery is
                -- LEFT JOINed to res_company (not filtered via WHERE
                -- directly) so a company with zero cash-account activity
                -- still gets a zero-balance row instead of no row at all.
                SELECT
                    c.id AS company_id,
                    c.currency_id AS currency_id,
                    COALESCE(cash_sum.balance, 0.0) AS balance
                FROM res_company c
                LEFT JOIN (
                    SELECT aml.company_id AS company_id, SUM(aml.balance) AS balance
                    FROM account_move_line aml
                    JOIN account_account aa ON aa.id = aml.account_id
                    JOIN account_move am ON am.id = aml.move_id
                    WHERE aa.account_type = 'asset_cash' AND am.state = 'posted'
                    GROUP BY aml.company_id
                ) cash_sum ON cash_sum.company_id = c.id
            ),
            customer_invoice AS (
                -- Sourced per receivable line (not per invoice header) so that
                -- invoices on a multi-installment payment term (e.g. 30-40-30)
                -- split their residual across each installment's own due date,
                -- instead of dumping the whole residual onto one date.
                SELECT
                    aml.id AS line_id,
                    aml.move_id AS move_id,
                    am.company_id AS company_id,
                    am.currency_id AS currency_id,
                    aml.partner_id AS partner_id,
                    am.name AS name,
                    COALESCE(aml.date_maturity, am.invoice_date_due, am.invoice_date, CURRENT_DATE) AS due_date,
                    aml.amount_residual AS net_amount
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN account_account aa ON aa.id = aml.account_id
                WHERE am.move_type = 'out_invoice'
                  AND am.state = 'posted'
                  AND aa.account_type = 'asset_receivable'
                  AND aml.reconciled IS FALSE
                  AND aml.amount_residual > 0.01
            ),
            vendor_bill AS (
                -- Same per-line rationale as customer_invoice above.
                SELECT
                    aml.id AS line_id,
                    aml.move_id AS move_id,
                    am.company_id AS company_id,
                    am.currency_id AS currency_id,
                    aml.partner_id AS partner_id,
                    am.name AS name,
                    COALESCE(aml.date_maturity, am.invoice_date_due, am.invoice_date, CURRENT_DATE) AS due_date,
                    -aml.amount_residual AS net_amount
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN account_account aa ON aa.id = aml.account_id
                WHERE am.move_type = 'in_invoice'
                  AND am.state = 'posted'
                  AND aa.account_type = 'liability_payable'
                  AND aml.reconciled IS FALSE
                  AND aml.amount_residual < -0.01
            ),
            sale_order_invoiced AS (
                -- Total of posted invoices linked back to each sale order,
                -- deduplicated per invoice (an invoice can touch multiple
                -- order lines from the same order). Works correctly even
                -- for down payments: a down-payment invoice is linked via a
                -- synthetic order line (is_downpayment=True) that never
                -- moves the real product lines' qty_invoiced, so a
                -- qty-based "remaining" calc would have kept showing the
                -- full order total even after the down payment posted -
                -- confirmed locally by actually creating one via the real
                -- sale.advance.payment.inv wizard. This monetary sum
                -- doesn't have that problem: it's exactly the down
                -- payment's own posted amount, whatever product/qty it
                -- notionally represents.
                SELECT sub.order_id, SUM(sub.amount_total) AS already_invoiced
                FROM (
                    SELECT DISTINCT sol.order_id, am.id AS move_id, am.amount_total
                    FROM sale_order_line sol
                    JOIN sale_order_line_invoice_rel rel ON rel.order_line_id = sol.id
                    JOIN account_move_line aml ON aml.id = rel.invoice_line_id
                    JOIN account_move am ON am.id = aml.move_id
                    WHERE am.state = 'posted' AND am.move_type = 'out_invoice'
                ) sub
                GROUP BY sub.order_id
            ),
            purchase_order_invoiced AS (
                -- Same rationale as sale_order_invoiced, via
                -- account_move_line.purchase_line_id instead of a relation
                -- table (purchase bill lines link directly, no M2M needed).
                SELECT sub.order_id, SUM(sub.amount_total) AS already_invoiced
                FROM (
                    SELECT DISTINCT pol.order_id, am.id AS move_id, am.amount_total
                    FROM purchase_order_line pol
                    JOIN account_move_line aml ON aml.purchase_line_id = pol.id
                    JOIN account_move am ON am.id = aml.move_id
                    WHERE am.state = 'posted' AND am.move_type = 'in_invoice'
                ) sub
                GROUP BY sub.order_id
            ),
            sale_order_src AS (
                -- Branch A: nothing posted-invoiced against this order yet -
                -- one row per payment-term installment (falls back to one
                -- row for the whole order_total if no payment term is set),
                -- same rationale as customer_invoice's per-installment
                -- split. Anchored on date_order (no delivery/invoice date
                -- exists yet). Unchanged from the previous version, just
                -- gated by "not yet invoiced" via sale_order_invoiced.
                SELECT * FROM (
                    SELECT
                        (so.id::bigint * 100 + ROW_NUMBER() OVER (
                            PARTITION BY so.id ORDER BY COALESCE(ptl.nb_days, 0), ptl.id
                        )) AS row_key,
                        so.id AS order_id,
                        so.company_id AS company_id,
                        so.currency_id AS currency_id,
                        so.partner_id AS partner_id,
                        so.name AS name,
                        NULL::numeric AS already_invoiced_amount,
                        (CASE
                            WHEN ptl.id IS NOT NULL THEN so.date_order::date + ptl.nb_days * INTERVAL '1 day'
                            WHEN so.commitment_date IS NOT NULL THEN so.commitment_date::date
                            ELSE so.date_order::date + c.cash_forecast_default_payment_days * INTERVAL '1 day'
                        END)::date AS due_date,
                        (CASE
                            WHEN ptl.id IS NULL THEN so.amount_total
                            WHEN ptl.value = 'fixed' THEN ptl.value_amount
                            ELSE so.amount_total * ptl.value_amount / 100.0
                        END) AS net_amount
                    FROM sale_order so
                    JOIN res_company c ON c.id = so.company_id
                    LEFT JOIN sale_order_invoiced inv ON inv.order_id = so.id
                    LEFT JOIN account_payment_term_line ptl ON ptl.payment_id = so.payment_term_id
                    WHERE so.state = 'sale'
                      AND so.currency_id = c.currency_id
                      AND so.amount_total > 0.01
                      AND COALESCE(inv.already_invoiced, 0) <= 0.01
                ) t
                WHERE t.net_amount > 0.01

                UNION ALL

                -- Branch B: SOME (but not all) of the order has been
                -- posted-invoiced already (a down payment, a partial
                -- delivery invoice, or both) - one row for what's left,
                -- order_total minus already_invoiced. Not split by
                -- installment: once real invoicing has started, the
                -- order's original payment-term schedule no longer cleanly
                -- maps to what remains (a down payment can carry its own,
                -- unrelated payment term - confirmed locally). Uses the
                -- same single-date fallback as before this change (furthest
                -- installment day-count, then commitment_date, then the
                -- default-days setting) rather than a new heuristic.
                SELECT * FROM (
                    SELECT
                        (so.id::bigint * 100 + 1) AS row_key,
                        so.id AS order_id,
                        so.company_id AS company_id,
                        so.currency_id AS currency_id,
                        so.partner_id AS partner_id,
                        so.name AS name,
                        inv.already_invoiced AS already_invoiced_amount,
                        (CASE
                            WHEN MAX(ptl.nb_days) IS NOT NULL
                                THEN so.date_order::date + MAX(ptl.nb_days) * INTERVAL '1 day'
                            WHEN so.commitment_date IS NOT NULL THEN so.commitment_date::date
                            ELSE so.date_order::date + c.cash_forecast_default_payment_days * INTERVAL '1 day'
                        END)::date AS due_date,
                        (so.amount_total - inv.already_invoiced) AS net_amount
                    FROM sale_order so
                    JOIN res_company c ON c.id = so.company_id
                    JOIN sale_order_invoiced inv ON inv.order_id = so.id AND inv.already_invoiced > 0.01
                    LEFT JOIN account_payment_term_line ptl ON ptl.payment_id = so.payment_term_id
                    WHERE so.state = 'sale'
                      AND so.currency_id = c.currency_id
                    GROUP BY so.id, so.company_id, so.currency_id, so.partner_id, so.name,
                             so.date_order, so.commitment_date, so.amount_total,
                             c.cash_forecast_default_payment_days, inv.already_invoiced
                ) t
                WHERE t.net_amount > 0.01
            ),
            purchase_order_src AS (
                -- Same two-branch rationale as sale_order_src, but anchored
                -- on the expected delivery date (MIN(date_planned) across
                -- lines) instead of date_order when a payment term is set -
                -- "pay for what we received".
                SELECT * FROM (
                    SELECT
                        (po.id::bigint * 100 + ROW_NUMBER() OVER (
                            PARTITION BY po.id ORDER BY COALESCE(ptl.nb_days, 0), ptl.id
                        )) AS row_key,
                        po.id AS order_id,
                        po.company_id AS company_id,
                        po.currency_id AS currency_id,
                        po.partner_id AS partner_id,
                        po.name AS name,
                        NULL::numeric AS already_invoiced_amount,
                        (CASE
                            WHEN ptl.id IS NOT NULL AND planned.planned_date IS NOT NULL
                                THEN planned.planned_date::date + ptl.nb_days * INTERVAL '1 day'
                            WHEN ptl.id IS NOT NULL
                                THEN po.date_order::date + ptl.nb_days * INTERVAL '1 day'
                            WHEN planned.planned_date IS NOT NULL THEN planned.planned_date::date
                            ELSE po.date_order::date + c.cash_forecast_default_payment_days * INTERVAL '1 day'
                        END)::date AS due_date,
                        (CASE
                            WHEN ptl.id IS NULL THEN po.amount_total
                            WHEN ptl.value = 'fixed' THEN ptl.value_amount
                            ELSE po.amount_total * ptl.value_amount / 100.0
                        END) AS net_amount
                    FROM purchase_order po
                    JOIN res_company c ON c.id = po.company_id
                    LEFT JOIN (
                        SELECT pol.order_id, MIN(pol.date_planned) AS planned_date
                        FROM purchase_order_line pol
                        WHERE pol.display_type IS NULL
                        GROUP BY pol.order_id
                    ) planned ON planned.order_id = po.id
                    LEFT JOIN purchase_order_invoiced inv ON inv.order_id = po.id
                    LEFT JOIN account_payment_term_line ptl ON ptl.payment_id = po.payment_term_id
                    WHERE po.state = 'purchase'
                      AND po.currency_id = c.currency_id
                      AND po.amount_total > 0.01
                      AND COALESCE(inv.already_invoiced, 0) <= 0.01
                ) t
                WHERE t.net_amount > 0.01

                UNION ALL

                SELECT * FROM (
                    SELECT
                        (po.id::bigint * 100 + 1) AS row_key,
                        po.id AS order_id,
                        po.company_id AS company_id,
                        po.currency_id AS currency_id,
                        po.partner_id AS partner_id,
                        po.name AS name,
                        inv.already_invoiced AS already_invoiced_amount,
                        (CASE
                            WHEN MAX(ptl.nb_days) IS NOT NULL AND MAX(planned.planned_date) IS NOT NULL
                                THEN MAX(planned.planned_date)::date + MAX(ptl.nb_days) * INTERVAL '1 day'
                            WHEN MAX(ptl.nb_days) IS NOT NULL
                                THEN po.date_order::date + MAX(ptl.nb_days) * INTERVAL '1 day'
                            WHEN MAX(planned.planned_date) IS NOT NULL THEN MAX(planned.planned_date)::date
                            ELSE po.date_order::date + c.cash_forecast_default_payment_days * INTERVAL '1 day'
                        END)::date AS due_date,
                        (po.amount_total - inv.already_invoiced) AS net_amount
                    FROM purchase_order po
                    JOIN res_company c ON c.id = po.company_id
                    JOIN purchase_order_invoiced inv ON inv.order_id = po.id AND inv.already_invoiced > 0.01
                    LEFT JOIN (
                        SELECT pol.order_id, MIN(pol.date_planned) AS planned_date
                        FROM purchase_order_line pol
                        WHERE pol.display_type IS NULL
                        GROUP BY pol.order_id
                    ) planned ON planned.order_id = po.id
                    LEFT JOIN account_payment_term_line ptl ON ptl.payment_id = po.payment_term_id
                    WHERE po.state = 'purchase'
                      AND po.currency_id = c.currency_id
                    GROUP BY po.id, po.company_id, po.currency_id, po.partner_id, po.name,
                             po.date_order, po.amount_total,
                             c.cash_forecast_default_payment_days, inv.already_invoiced
                ) t
                WHERE t.net_amount > 0.01
            ),
            unioned AS (
                SELECT
                    company_id * 10 + 0 AS id,
                    company_id,
                    currency_id,
                    'opening_balance'::varchar AS source_type,
                    'opening'::varchar AS direction,
                    NULL::integer AS partner_id,
                    NULL::integer AS move_id,
                    NULL::integer AS sale_order_id,
                    NULL::integer AS purchase_order_id,
                    'Opening Balance'::varchar AS name,
                    NULL::numeric AS already_invoiced_amount,
                    CURRENT_DATE AS original_due_date,
                    CURRENT_DATE AS bucket_date,
                    false AS is_overdue,
                    GREATEST(balance, 0) AS amount_in,
                    GREATEST(-balance, 0) AS amount_out,
                    balance AS net_amount
                FROM opening_balance

                UNION ALL

                SELECT
                    line_id * 10 + 1 AS id,
                    company_id,
                    currency_id,
                    'customer_invoice'::varchar AS source_type,
                    'in'::varchar AS direction,
                    partner_id,
                    move_id,
                    NULL::integer AS sale_order_id,
                    NULL::integer AS purchase_order_id,
                    name,
                    NULL::numeric AS already_invoiced_amount,
                    due_date AS original_due_date,
                    GREATEST(due_date, CURRENT_DATE) AS bucket_date,
                    due_date < CURRENT_DATE AS is_overdue,
                    net_amount AS amount_in,
                    0 AS amount_out,
                    net_amount
                FROM customer_invoice

                UNION ALL

                SELECT
                    line_id * 10 + 2 AS id,
                    company_id,
                    currency_id,
                    'vendor_bill'::varchar AS source_type,
                    'out'::varchar AS direction,
                    partner_id,
                    move_id,
                    NULL::integer AS sale_order_id,
                    NULL::integer AS purchase_order_id,
                    name,
                    NULL::numeric AS already_invoiced_amount,
                    due_date AS original_due_date,
                    GREATEST(due_date, CURRENT_DATE) AS bucket_date,
                    due_date < CURRENT_DATE AS is_overdue,
                    0 AS amount_in,
                    net_amount AS amount_out,
                    -net_amount AS net_amount
                FROM vendor_bill

                UNION ALL

                SELECT
                    row_key * 10 + 3 AS id,
                    company_id,
                    currency_id,
                    'sale_order'::varchar AS source_type,
                    'in'::varchar AS direction,
                    partner_id,
                    NULL::integer AS move_id,
                    order_id AS sale_order_id,
                    NULL::integer AS purchase_order_id,
                    name,
                    already_invoiced_amount,
                    due_date AS original_due_date,
                    GREATEST(due_date, CURRENT_DATE) AS bucket_date,
                    due_date < CURRENT_DATE AS is_overdue,
                    net_amount AS amount_in,
                    0 AS amount_out,
                    net_amount
                FROM sale_order_src

                UNION ALL

                SELECT
                    row_key * 10 + 4 AS id,
                    company_id,
                    currency_id,
                    'purchase_order'::varchar AS source_type,
                    'out'::varchar AS direction,
                    partner_id,
                    NULL::integer AS move_id,
                    NULL::integer AS sale_order_id,
                    order_id AS purchase_order_id,
                    name,
                    already_invoiced_amount,
                    due_date AS original_due_date,
                    GREATEST(due_date, CURRENT_DATE) AS bucket_date,
                    due_date < CURRENT_DATE AS is_overdue,
                    0 AS amount_in,
                    net_amount AS amount_out,
                    -net_amount AS net_amount
                FROM purchase_order_src
            )
            SELECT
                id,
                company_id,
                currency_id,
                source_type,
                direction,
                partner_id,
                move_id,
                sale_order_id,
                purchase_order_id,
                name,
                already_invoiced_amount,
                original_due_date,
                bucket_date,
                is_overdue,
                amount_in,
                amount_out,
                net_amount,
                SUM(net_amount) OVER (
                    PARTITION BY company_id
                    ORDER BY bucket_date, id
                    ROWS UNBOUNDED PRECEDING
                ) AS running_balance
            FROM unioned
            )
        """ % {'table': self._table})
