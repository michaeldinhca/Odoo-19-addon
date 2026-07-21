import base64
import io

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CashFlowForecastScenario(models.Model):
    """A user-triggered, persisted snapshot of the cash flow forecast, built
    by copying rows out of the live ``cash.flow.forecast.report`` SQL view
    for a chosen horizon. Re-running (``action_run``) wipes and rebuilds
    ``line_ids``/``trend_line_ids``, the same UX as Odoo's own asset
    depreciation board.

    ``method`` dispatches to ``_run_<method>()`` by name, so a new method is
    just a new Selection option + a new ``_run_`` method, no dispatch
    changes needed. Two methods so far:
    - ``confirmed_documents``: deterministic, built from real posted
      invoices/bills/orders (see ``cash.flow.forecast.report``).
    - ``historical_trend``: predictive, a trailing weekly average of
      REALIZED cash flow (see ``cash.flow.actual.daily``), projected flat
      forward with a min/max range - deliberately not seasonal/ML-based
      yet, since this module doesn't have enough history for that to be
      reliable rather than overfit noise.
    """

    _name = 'cash.flow.forecast.scenario'
    _description = 'Cash Flow Forecast Scenario'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, default='New Forecast Scenario')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    method = fields.Selection([
        ('confirmed_documents', 'Confirmed Documents (Invoices, Bills, Sales & Purchase Orders)'),
        ('historical_trend', 'Historical Trend (Predictive)'),
    ], string='Method', required=True, default='confirmed_documents')
    horizon = fields.Selection([
        ('30', 'Next 30 Days'),
        ('60', 'Next 60 Days'),
        ('90', 'Next 90 Days'),
        ('180', 'Next 180 Days'),
    ], string='Forecast Horizon', required=True, default='90')
    trend_lookback_weeks = fields.Selection([
        ('4', 'Last 4 Weeks'),
        ('8', 'Last 8 Weeks'),
        ('12', 'Last 12 Weeks'),
        ('26', 'Last 26 Weeks'),
    ], string='Lookback Period', default='12',
        help="Only used by the Historical Trend method: how far back to "
             "look at realized bank/cash activity when computing the "
             "trailing weekly average.")
    computed_on = fields.Datetime(readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency')
    opening_balance_override = fields.Monetary(
        string='Opening Balance Override',
        currency_field='currency_id',
        help="Leave blank to compute the opening balance automatically from "
             "posted bank/cash account balances. Set a value here to use it "
             "directly instead - useful as a fail-safe if the automatic "
             "figure doesn't match your actual bank balance. Used by both "
             "forecasting methods.",
    )
    biweekly_salary_amount = fields.Monetary(
        string='Bi-Weekly Salary (Outgoing)',
        currency_field='currency_id',
        help="Optional recurring outgoing amount (e.g. payroll) not "
             "captured by either forecasting method, since it isn't backed "
             "by a posted bill or by historical bank activity yet. Added as "
             "an extra outgoing cash flow every 14 days starting from the "
             "Next Salary Date, through the forecast horizon. Leave at 0 to "
             "ignore. Used by both forecasting methods.",
    )
    biweekly_salary_start_date = fields.Date(
        string='Next Salary Date',
        help="Anchor date for the recurring bi-weekly salary outgoing - "
             "occurrences repeat every 14 days from this date (only future "
             "occurrences, from today onward, are added to the forecast). "
             "Only used when Bi-Weekly Salary is set.",
    )
    line_ids = fields.One2many('cash.flow.forecast.scenario.line', 'scenario_id', string='Forecast Lines')
    trend_line_ids = fields.One2many(
        'cash.flow.forecast.scenario.trend.line', 'scenario_id', string='Predictive Forecast Lines',
    )

    def action_run(self):
        # cash.flow.forecast.report/cash.flow.actual.daily are raw SQL views
        # with no ORM-visible field dependency on account.move/sale.order/
        # purchase.order, so they won't be auto-flushed before the search()
        # calls in _run_confirmed_documents/_run_historical_trend the way a
        # normal computed field would be. Flushing explicitly here guards
        # against reading stale data if something was just created/posted
        # earlier in the same transaction.
        self.env.flush_all()
        for scenario in self:
            scenario.line_ids.unlink()
            scenario.trend_line_ids.unlink()
            method_name = '_run_%s' % scenario.method
            run_method = getattr(scenario, method_name, None)
            if run_method is None:
                raise UserError(_("No implementation found for forecast method '%s'.") % scenario.method)
            run_method()
            scenario.computed_on = fields.Datetime.now()
            method_label = dict(scenario._fields['method'].selection).get(scenario.method, scenario.method)
            horizon_label = dict(scenario._fields['horizon'].selection).get(scenario.horizon, scenario.horizon)
            scenario.message_post(body=_(
                "Forecast computed by %s using method \"%s\" for %s."
            ) % (self.env.user.name, method_label, horizon_label))
        return True

    def action_export_xlsx(self):
        # Pattern matches Odoo core's own xlsx-download buttons (e.g.
        # account.report.action_download_xlsx_accounts_coverage_report):
        # build the file in memory with xlsxwriter, store it as an
        # ir.attachment, and return an ir.actions.act_url with
        # target="download" to trigger the browser download.
        self.ensure_one()
        import xlsxwriter  # noqa: PLC0415

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(_('Forecast Lines'))

        bold = workbook.add_format({'bold': True})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9'})
        money_format = workbook.add_format({'num_format': '#,##0.00'})

        method_label = dict(self._fields['method'].selection).get(self.method, self.method)
        horizon_label = dict(self._fields['horizon'].selection).get(self.horizon, self.horizon)

        sheet.write(0, 0, _('Scenario'), bold)
        sheet.write(0, 1, self.name)
        sheet.write(1, 0, _('Method'), bold)
        sheet.write(1, 1, method_label)
        sheet.write(2, 0, _('Forecast Horizon'), bold)
        sheet.write(2, 1, horizon_label)
        sheet.write(3, 0, _('Computed On'), bold)
        sheet.write(3, 1, fields.Datetime.to_string(self.computed_on) if self.computed_on else '')

        if self.method == 'historical_trend':
            headers = [
                _('Description'), _('Week Start'), _('Incoming (Min)'), _('Incoming (Avg)'), _('Incoming (Max)'),
                _('Outgoing (Min)'), _('Outgoing (Avg)'), _('Outgoing (Max)'),
                _('Net (Avg)'), _('Forecasted Balance (Avg)'),
            ]
            header_row = 5
            for col, header in enumerate(headers):
                sheet.write(header_row, col, header, header_format)
            for row, line in enumerate(self.trend_line_ids.sorted('sequence'), start=header_row + 1):
                sheet.write(row, 0, line.name or '')
                sheet.write(row, 1, line.week_start_date.isoformat() if line.week_start_date else '')
                sheet.write_number(row, 2, line.amount_in_min, money_format)
                sheet.write_number(row, 3, line.amount_in_avg, money_format)
                sheet.write_number(row, 4, line.amount_in_max, money_format)
                sheet.write_number(row, 5, line.amount_out_min, money_format)
                sheet.write_number(row, 6, line.amount_out_avg, money_format)
                sheet.write_number(row, 7, line.amount_out_max, money_format)
                sheet.write_number(row, 8, line.net_avg, money_format)
                sheet.write_number(row, 9, line.running_balance_avg, money_format)
        else:
            headers = [
                _('Forecast Date'), _('Source'), _('Partner'), _('Description'),
                _('Incoming'), _('Outgoing'), _('Net Amount'), _('Forecasted Balance'),
            ]
            header_row = 5
            for col, header in enumerate(headers):
                sheet.write(header_row, col, header, header_format)
            source_labels = dict(self.env['cash.flow.forecast.scenario.line']._fields['source_type'].selection)
            for row, line in enumerate(self.line_ids.sorted('sequence'), start=header_row + 1):
                sheet.write(row, 0, line.bucket_date.isoformat() if line.bucket_date else '')
                sheet.write(row, 1, source_labels.get(line.source_type, line.source_type or ''))
                sheet.write(row, 2, line.partner_id.name or '')
                sheet.write(row, 3, line.name or '')
                sheet.write_number(row, 4, line.amount_in, money_format)
                sheet.write_number(row, 5, line.amount_out, money_format)
                sheet.write_number(row, 6, line.net_amount, money_format)
                sheet.write_number(row, 7, line.running_balance, money_format)

        workbook.close()
        attachment = self.env['ir.attachment'].create({
            'name': '%s.xlsx' % self.name,
            'datas': base64.encodebytes(output.getvalue()),
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s' % attachment.id,
            'target': 'download',
        }

    def _get_opening_balance_breakdown_text(self):
        """Per-journal breakdown of the computed opening balance, e.g.
        "Bank: 4,190.93, Cash: 0.00" - lets a user trace the total back to
        which specific journal(s) it came from, instead of just seeing one
        lump sum. Grouped by journal (not by G/L account) since that's the
        concept users actually navigate by in Accounting. Still uses the
        same account_type = 'asset_cash' filter as the cash_flow_forecast_report
        view's opening_balance CTE, so the breakdown always adds up to the
        same total shown there.
        """
        self.ensure_one()
        groups = self.env['account.move.line']._read_group(
            domain=[
                ('company_id', '=', self.company_id.id),
                ('account_id.account_type', '=', 'asset_cash'),
                ('move_id.state', '=', 'posted'),
            ],
            groupby=['journal_id'],
            aggregates=['balance:sum'],
        )
        if not groups:
            return _('no bank/cash journals with posted activity')
        return ', '.join(
            '%s: %.2f' % (journal.name, balance)
            for journal, balance in sorted(groups, key=lambda g: g[0].name)
        )

    def _get_opening_balance(self):
        """(amount, description) for this scenario's opening balance: the
        manual override if set, otherwise the live cash.flow.forecast.report
        view's own auto-computed opening_balance row (same asset_cash-based
        calculation used everywhere in this module - one source of truth).
        Shared by both _run_confirmed_documents and _run_historical_trend so
        there's exactly one place that decides "what's the starting cash".
        """
        self.ensure_one()
        auto_row = self.env['cash.flow.forecast.report'].search([
            ('company_id', '=', self.company_id.id),
            ('source_type', '=', 'opening_balance'),
        ], limit=1)
        auto_amount = auto_row.net_amount if auto_row else 0.0
        if self.opening_balance_override:
            return self.opening_balance_override, _('Opening Balance (Manual Override)')
        description = _('Opening Balance (Computed from Bank/Cash Accounts: %s)') % (
            self._get_opening_balance_breakdown_text()
        )
        return auto_amount, description

    def _get_biweekly_salary_dates(self, range_start, range_end):
        """Dates within [range_start, range_end] (inclusive) that the
        recurring bi-weekly salary outgoing falls on, anchored to
        biweekly_salary_start_date and repeating every 14 days. Returns an
        empty list if the setting isn't configured (amount or date blank).
        Shared by both forecasting methods so a salary occurrence can never
        land on different dates depending on which method is running.
        """
        self.ensure_one()
        if not self.biweekly_salary_amount or not self.biweekly_salary_start_date:
            return []
        anchor = self.biweekly_salary_start_date
        if anchor >= range_start:
            first = anchor
        else:
            days_since = (range_start - anchor).days
            periods_elapsed = -(-days_since // 14)  # ceil division
            first = anchor + relativedelta(days=periods_elapsed * 14)
        dates = []
        current = first
        while current <= range_end:
            dates.append(current)
            current += relativedelta(days=14)
        return dates

    def _get_installment_doc_key(self, report_line):
        """Identifies which source document a report row belongs to, so
        rows split across multiple payment-term installments (invoices,
        bills, sale orders, purchase orders - see cash_flow_forecast_report.py)
        can be numbered "installment #1", "installment #2", etc.
        """
        if report_line.source_type in ('customer_invoice', 'vendor_bill') and report_line.move_id:
            return ('move', report_line.move_id.id)
        if report_line.source_type == 'sale_order' and report_line.sale_order_id:
            return ('sale_order', report_line.sale_order_id.id)
        if report_line.source_type == 'purchase_order' and report_line.purchase_order_id:
            return ('purchase_order', report_line.purchase_order_id.id)
        return None

    def _run_confirmed_documents(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        cutoff = today + relativedelta(days=int(self.horizon))
        report_lines = self.env['cash.flow.forecast.report'].search([
            ('company_id', '=', self.company_id.id),
            ('bucket_date', '<=', cutoff),
        ], order='bucket_date asc, id asc')

        # Multi-installment invoices/bills/orders produce several report rows
        # sharing the same source document (see cash_flow_forecast_report.py)
        # - count them per document so each row's description can say
        # "installment #1", "installment #2", etc., matching Odoo's own
        # native journal-item label style for split payment terms.
        installment_totals = {}
        for report_line in report_lines:
            key = self._get_installment_doc_key(report_line)
            if key:
                installment_totals[key] = installment_totals.get(key, 0) + 1

        opening_amount, opening_description = self._get_opening_balance()

        # Build every non-opening row (document-sourced + any bi-weekly
        # salary occurrences) without a running balance first, then sort
        # them together by date - a salary occurrence isn't known to the
        # cash.flow.forecast.report view, so the view's own running_balance
        # column can no longer be trusted (not even with a constant
        # opening-balance offset, since salary rows shift every later row
        # by a varying amount depending on how many occurrences precede it).
        installment_counters = {}
        entries = []
        for report_line in report_lines:
            if report_line.source_type == 'opening_balance':
                continue
            description = report_line.name or ''
            # Prefix with the originating document (e.g. the sale
            # order that generated this invoice), matching Odoo's
            # own native label style: "S00026 - INV/2026/00012".
            if report_line.source_type in ('customer_invoice', 'vendor_bill') \
                    and report_line.move_id and report_line.move_id.invoice_origin:
                description = '%s - %s' % (report_line.move_id.invoice_origin, description)
            # An order that's already partially invoiced/billed (a
            # down payment, a partial delivery invoice, or both)
            # gets a single row for what's left - label it distinctly
            # from a fresh, not-yet-invoiced order.
            if report_line.source_type == 'sale_order' and report_line.already_invoiced_amount:
                description = _('%s - Remaining to Invoice') % description
            elif report_line.source_type == 'purchase_order' and report_line.already_invoiced_amount:
                description = _('%s - Remaining to Bill') % description
            key = self._get_installment_doc_key(report_line)
            if key and installment_totals.get(key, 1) > 1:
                installment_counters[key] = installment_counters.get(key, 0) + 1
                idx = installment_counters[key]
                description = _('%s installment #%d') % (description, idx)
            if report_line.is_overdue:
                description = _('%s ⚠️ Overdue') % description

            entries.append({
                'bucket_date': report_line.bucket_date,
                'company_id': report_line.company_id.id,
                'currency_id': report_line.currency_id.id,
                'source_type': report_line.source_type,
                'direction': report_line.direction,
                'partner_id': report_line.partner_id.id,
                'move_id': report_line.move_id.id,
                'sale_order_id': report_line.sale_order_id.id,
                'purchase_order_id': report_line.purchase_order_id.id,
                'name': description,
                'original_due_date': report_line.original_due_date,
                'is_overdue': report_line.is_overdue,
                'amount_in': report_line.amount_in,
                'amount_out': report_line.amount_out,
                'net_amount': report_line.net_amount,
            })

        for salary_date in self._get_biweekly_salary_dates(today, cutoff):
            entries.append({
                'bucket_date': salary_date,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                'source_type': 'salary',
                'direction': 'out',
                'partner_id': False,
                'move_id': False,
                'sale_order_id': False,
                'purchase_order_id': False,
                'name': _('Bi-Weekly Salary'),
                'original_due_date': salary_date,
                'is_overdue': False,
                'amount_in': 0.0,
                'amount_out': self.biweekly_salary_amount,
                'net_amount': -self.biweekly_salary_amount,
            })

        entries.sort(key=lambda e: e['bucket_date'])

        line_vals = [{
            'scenario_id': self.id,
            'sequence': 0,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'source_type': 'opening_balance',
            'direction': 'opening',
            'name': opening_description,
            'bucket_date': today,
            'amount_in': max(opening_amount, 0.0),
            'amount_out': max(-opening_amount, 0.0),
            'net_amount': opening_amount,
            'running_balance': opening_amount,
        }]
        running = opening_amount
        for sequence, entry in enumerate(entries, start=1):
            running += entry['net_amount']
            entry['scenario_id'] = self.id
            entry['sequence'] = sequence
            entry['running_balance'] = running
            line_vals.append(entry)

        self.env['cash.flow.forecast.scenario.line'].create(line_vals)

    def _run_historical_trend(self):
        """Predictive method: trailing weekly average of REALIZED cash flow
        (cash.flow.actual.daily), incoming and outgoing averaged separately,
        projected flat forward for the scenario's horizon. Deliberately no
        seasonal/trend-slope modeling - see class docstring.
        """
        self.ensure_one()
        lookback_weeks = int(self.trend_lookback_weeks)
        today = fields.Date.context_today(self)
        history_start = today - relativedelta(weeks=lookback_weeks)

        daily_rows = self.env['cash.flow.actual.daily'].search([
            ('company_id', '=', self.company_id.id),
            ('activity_date', '>=', history_start),
            ('activity_date', '<', today),
        ])

        weekly_in = {}
        weekly_out = {}
        for row in daily_rows:
            week_start = row.activity_date - relativedelta(days=row.activity_date.weekday())
            weekly_in[week_start] = weekly_in.get(week_start, 0.0) + row.amount_in
            weekly_out[week_start] = weekly_out.get(week_start, 0.0) + row.amount_out

        all_weeks = sorted(set(weekly_in) | set(weekly_out))
        if len(all_weeks) < 2:
            raise UserError(_(
                "Not enough historical bank/cash activity to compute a "
                "trend - need at least 2 distinct weeks of posted activity "
                "within the lookback period. Try a longer lookback period, "
                "or use the Confirmed Documents method instead."
            ))

        in_values = [weekly_in.get(w, 0.0) for w in all_weeks]
        out_values = [weekly_out.get(w, 0.0) for w in all_weeks]
        avg_in, min_in, max_in = sum(in_values) / len(in_values), min(in_values), max(in_values)
        avg_out, min_out, max_out = sum(out_values) / len(out_values), min(out_values), max(out_values)

        opening_amount, opening_description = self._get_opening_balance()

        # Reconstruct the real (not averaged) running balance for each
        # historical week, walking backward from the shared opening balance:
        # the newest week's ending balance IS opening_amount (nothing
        # happened between the end of that week and "today"), then each
        # earlier week's ending balance is the next week's minus that next
        # week's own net movement. Self-consistent with a manual override
        # too - the override is "trust this as today's truth," and this
        # walk is relative to it, not a second independent ledger read.
        running_hist = {}
        balance = opening_amount
        for week in reversed(all_weeks):
            running_hist[week] = balance
            balance -= (weekly_in.get(week, 0.0) - weekly_out.get(week, 0.0))

        line_vals = []
        sequence = 0
        for week in all_weeks:
            week_in = weekly_in.get(week, 0.0)
            week_out = weekly_out.get(week, 0.0)
            line_vals.append({
                'scenario_id': self.id,
                'sequence': sequence,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                'row_type': 'historical',
                'week_start_date': week,
                'week_end_date': week + relativedelta(days=6),
                'amount_in_avg': week_in,
                'amount_in_min': week_in,
                'amount_in_max': week_in,
                'amount_out_avg': week_out,
                'amount_out_min': week_out,
                'amount_out_max': week_out,
                'net_avg': week_in - week_out,
                'running_balance_avg': running_hist[week],
            })
            sequence += 1

        line_vals.append({
            'scenario_id': self.id,
            'sequence': sequence,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'row_type': 'opening_balance',
            'name': opening_description,
            'amount_in_avg': 0.0,
            'amount_in_min': 0.0,
            'amount_in_max': 0.0,
            'amount_out_avg': 0.0,
            'amount_out_min': 0.0,
            'amount_out_max': 0.0,
            'net_avg': 0.0,
            'running_balance_avg': opening_amount,
        })
        sequence += 1

        horizon_days = int(self.horizon)
        num_weeks = -(-horizon_days // 7)  # ceil division, no full week left uncovered

        # Bucketed the same way the projected weeks themselves are bucketed
        # (today + N*7 days, not Monday-aligned like the historical weeks
        # above) so a salary occurrence always lands in the same projected
        # row it's displayed alongside.
        projection_end = today + relativedelta(days=7 * num_weeks - 1)
        salary_by_week_index = {}
        for salary_date in self._get_biweekly_salary_dates(today, projection_end):
            week_index_for_date = (salary_date - today).days // 7
            salary_by_week_index[week_index_for_date] = (
                salary_by_week_index.get(week_index_for_date, 0.0) + self.biweekly_salary_amount
            )

        running = opening_amount
        for week_index in range(num_weeks):
            week_start = today + relativedelta(weeks=week_index)
            salary_out = salary_by_week_index.get(week_index, 0.0)
            week_out_avg = avg_out + salary_out
            week_out_min = min_out + salary_out
            week_out_max = max_out + salary_out
            week_net_avg = avg_in - week_out_avg
            running += week_net_avg
            line_vals.append({
                'scenario_id': self.id,
                'sequence': sequence + week_index,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                'row_type': 'projected',
                'name': _('Includes Bi-Weekly Salary') if salary_out else False,
                'week_start_date': week_start,
                'week_end_date': week_start + relativedelta(days=6),
                'amount_in_avg': avg_in,
                'amount_in_min': min_in,
                'amount_in_max': max_in,
                'amount_out_avg': week_out_avg,
                'amount_out_min': week_out_min,
                'amount_out_max': week_out_max,
                'net_avg': week_net_avg,
                'running_balance_avg': running,
            })
        self.env['cash.flow.forecast.scenario.trend.line'].create(line_vals)


class CashFlowForecastScenarioLine(models.Model):
    _name = 'cash.flow.forecast.scenario.line'
    _description = 'Cash Flow Forecast Scenario Line'
    _order = 'sequence asc'

    scenario_id = fields.Many2one('cash.flow.forecast.scenario', required=True, ondelete='cascade')
    sequence = fields.Integer()
    company_id = fields.Many2one('res.company')
    currency_id = fields.Many2one('res.currency')
    source_type = fields.Selection([
        ('opening_balance', 'Opening Balance'),
        ('customer_invoice', 'Customer Invoice'),
        ('vendor_bill', 'Vendor Bill'),
        ('sale_order', 'Sale Order'),
        ('purchase_order', 'Purchase Order'),
        ('salary', 'Bi-Weekly Salary'),
    ], string='Source')
    direction = fields.Selection([
        ('in', 'Incoming'),
        ('out', 'Outgoing'),
        ('opening', 'Opening'),
    ])
    partner_id = fields.Many2one('res.partner', string='Partner')
    move_id = fields.Many2one('account.move', string='Invoice/Bill')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order')
    name = fields.Char(string='Description')
    original_due_date = fields.Date()
    bucket_date = fields.Date(string='Forecast Date')
    is_overdue = fields.Boolean(string='Overdue')
    amount_in = fields.Monetary(string='Incoming', currency_field='currency_id')
    amount_out = fields.Monetary(string='Outgoing', currency_field='currency_id')
    net_amount = fields.Monetary(string='Net Amount', currency_field='currency_id')
    running_balance = fields.Monetary(string='Forecasted Balance', currency_field='currency_id')
    view_url = fields.Char(string='View', compute='_compute_view_url')

    @api.depends('move_id', 'sale_order_id', 'purchase_order_id')
    def _compute_view_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for line in self:
            record = line.move_id or line.sale_order_id or line.purchase_order_id
            if record:
                line.view_url = '%s/web#id=%d&model=%s&view_type=form' % (base_url, record.id, record._name)
            else:
                line.view_url = False


class CashFlowForecastScenarioTrendLine(models.Model):
    """Predictive-method output rows (see
    CashFlowForecastScenario._run_historical_trend). Deliberately a
    separate model from cash.flow.forecast.scenario.line rather than
    extending it with a pile of nullable fields either way: this shape has
    no partner_id/move_id/view_url equivalent (a trend row isn't backed by
    any specific document), but has min/avg/max ranges that confirmed-
    document rows don't need.
    """

    _name = 'cash.flow.forecast.scenario.trend.line'
    _description = 'Cash Flow Forecast Scenario Predictive Line'
    _order = 'sequence asc'

    scenario_id = fields.Many2one('cash.flow.forecast.scenario', required=True, ondelete='cascade')
    sequence = fields.Integer()
    company_id = fields.Many2one('res.company')
    currency_id = fields.Many2one('res.currency')
    row_type = fields.Selection([
        ('historical', 'Historical'),
        ('opening_balance', 'Opening Balance'),
        ('projected', 'Projected'),
    ], required=True)
    name = fields.Char(string='Description')
    week_start_date = fields.Date(string='Week Start')
    week_end_date = fields.Date(string='Week End')
    amount_in_avg = fields.Monetary(string='Incoming (Avg)', currency_field='currency_id')
    amount_in_min = fields.Monetary(string='Incoming (Min)', currency_field='currency_id')
    amount_in_max = fields.Monetary(string='Incoming (Max)', currency_field='currency_id')
    amount_out_avg = fields.Monetary(string='Outgoing (Avg)', currency_field='currency_id')
    amount_out_min = fields.Monetary(string='Outgoing (Min)', currency_field='currency_id')
    amount_out_max = fields.Monetary(string='Outgoing (Max)', currency_field='currency_id')
    net_avg = fields.Monetary(string='Net (Avg)', currency_field='currency_id')
    running_balance_avg = fields.Monetary(string='Forecasted Balance (Avg)', currency_field='currency_id')
