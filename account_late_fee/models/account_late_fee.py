import psycopg2
from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError


class AccountLateFee(models.Model):
    _name = 'account.late.fee'
    _description = 'Late Fee'
    _inherit = ['mail.thread']
    _order = 'computation_date desc, id desc'

    name = fields.Char(
        default=lambda self: _('New'), copy=False, readonly=True)
    active = fields.Boolean(default=True)

    invoice_line_id = fields.Many2one(
        'account.move.line', string='Overdue Installment', required=True,
        ondelete='restrict', copy=False,
        domain=[('display_type', '=', 'payment_term'),
                ('account_type', '=', 'asset_receivable')])
    move_id = fields.Many2one(
        'account.move', related='invoice_line_id.move_id', store=True,
        readonly=True, string='Invoice')
    partner_id = fields.Many2one(
        'res.partner', related='move_id.partner_id', store=True,
        readonly=True)
    company_id = fields.Many2one(
        'res.company', related='move_id.company_id', store=True,
        readonly=True)
    currency_id = fields.Many2one(
        'res.currency', related='move_id.currency_id', store=True,
        readonly=True)

    late_fee_model_id = fields.Many2one(
        'late.fee.model', required=True, ondelete='restrict')

    installment_sequence = fields.Integer(
        compute='_compute_installment_position', store=True)
    installment_count = fields.Integer(
        compute='_compute_installment_position', store=True)
    due_date = fields.Date(
        related='invoice_line_id.date_maturity', store=True, readonly=True)

    period_index = fields.Integer(required=True, default=1)
    computation_date = fields.Date(
        required=True, default=fields.Date.context_today)
    overdue_amount = fields.Monetary(
        currency_field='currency_id', required=True)
    overdue_days = fields.Integer(required=True)

    # Snapshots of the model configuration at the time this fee was
    # generated, so later edits to the Late Fee Model never rewrite the
    # explanation of a fee that was already charged.
    computation_type = fields.Selection(
        [('percentage', 'Percentage of Overdue Amount'),
         ('fixed', 'Fixed Amount')], readonly=True)
    rate_applied = fields.Float(digits=(5, 2), readonly=True)
    fixed_amount_applied = fields.Monetary(
        currency_field='currency_id', readonly=True)
    interval_type = fields.Selection(
        [('day', 'Day(s)'), ('week', 'Week(s)'), ('month', 'Month(s)')],
        readonly=True)
    application_mode = fields.Selection(
        [('same_invoice', 'Add Line to Same Invoice'),
         ('new_invoice', 'Create New Late Fee Invoice')], readonly=True)

    fee_amount = fields.Monetary(currency_field='currency_id', required=True)
    description = fields.Text(
        compute='_compute_description', store=True, readonly=False)

    state = fields.Selection(
        [('draft', 'To Review'), ('confirmed', 'Confirmed'),
         ('waived', 'Waived'), ('error', 'Error')],
        default='draft', required=True, tracking=True, copy=False)
    error_message = fields.Text(readonly=True, copy=False)

    fee_move_id = fields.Many2one(
        'account.move', string='Fee Invoice', readonly=True, copy=False)
    fee_invoice_line_id = fields.Many2one(
        'account.move.line', string='Fee Line', readonly=True, copy=False)

    confirmed_by = fields.Many2one(
        'res.users', readonly=True, copy=False)
    confirmed_date = fields.Datetime(readonly=True, copy=False)
    waived_by = fields.Many2one('res.users', readonly=True, copy=False)
    waived_date = fields.Datetime(readonly=True, copy=False)
    waive_reason = fields.Char(copy=False)
    mail_sent = fields.Boolean(default=False, readonly=True, copy=False)

    _uniq_line_period = models.Constraint(
        'unique(invoice_line_id, period_index)',
        'A late fee already exists for this installment and period.',
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('invoice_line_id', 'move_id.line_ids.date_maturity',
                 'move_id.line_ids.display_type')
    def _compute_installment_position(self):
        for fee in self:
            term_lines = fee.move_id.line_ids.filtered(
                lambda l: l.display_type == 'payment_term'
            ).sorted(lambda l: l.date_maturity or fields.Date.today())
            fee.installment_count = len(term_lines)
            fee.installment_sequence = (
                term_lines.ids.index(fee.invoice_line_id.id) + 1
                if fee.invoice_line_id.id in term_lines.ids else 0)

    @api.depends('fee_amount', 'overdue_amount', 'overdue_days',
                 'computation_type', 'rate_applied', 'fixed_amount_applied',
                 'application_mode', 'period_index', 'late_fee_model_id',
                 'installment_sequence', 'installment_count', 'due_date')
    def _compute_description(self):
        for fee in self:
            if fee.state != 'draft':
                continue
            fee.description = fee._build_description()

    def _build_description(self):
        self.ensure_one()
        currency_name = self.currency_id.name or ''

        if self.computation_type == 'percentage':
            calc = _(
                '%(rate)s%% of %(base)s %(cur)s overdue = %(fee)s %(cur)s',
                rate=self.rate_applied, base='%.2f' % self.overdue_amount,
                cur=currency_name, fee='%.2f' % self.fee_amount)
        else:
            calc = _(
                'Fixed late fee of %(fee)s %(cur)s',
                fee='%.2f' % self.fee_amount, cur=currency_name)

        recurrence_note = ''
        if self.period_index > 1:
            cap = self.late_fee_model_id.max_occurrences or _('unlimited')
            recurrence_note = _(
                ' (recurring charge, occurrence %(n)s of %(cap)s)',
                n=self.period_index, cap=cap)

        new_total = self.overdue_amount + self.fee_amount
        if self.application_mode == 'same_invoice':
            total_note = _(
                'New amount due for this installment: %(total)s %(cur)s.',
                total='%.2f' % new_total, cur=currency_name)
        else:
            total_note = _(
                'This fee is billed on a separate invoice. Combined '
                'amount now owed (original overdue installment + this '
                'fee): %(total)s %(cur)s.',
                total='%.2f' % new_total, cur=currency_name)

        text = _(
            'Late fee for Invoice %(invoice)s, Installment %(n)s of '
            '%(total)s (originally due %(due)s).\n'
            'Overdue amount: %(overdue)s %(cur)s — %(days)s day(s) '
            'overdue as of %(asof)s.\n'
            'Calculation: %(calc)s%(recur)s.\n'
            'Late fee charged: %(fee)s %(cur)s.\n'
            '%(total_note)s',
            invoice=self.move_id.name, n=self.installment_sequence or 1,
            total=self.installment_count or 1, due=self.due_date,
            overdue='%.2f' % self.overdue_amount, cur=currency_name,
            days=self.overdue_days, asof=self.computation_date, calc=calc,
            recur=recurrence_note, fee='%.2f' % self.fee_amount,
            total_note=total_note,
        )
        if self.late_fee_model_id.additional_note:
            text += '\n\n' + self.late_fee_model_id.additional_note
        return text

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('account.late.fee')
                    or _('New'))
        return super().create(vals_list)

    def write(self, vals):
        if {'fee_amount', 'description'} & set(vals):
            if self.filtered(lambda f: f.state != 'draft'):
                raise UserError(_(
                    'The amount/description of a confirmed or waived late '
                    'fee can no longer be edited.'))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Cron: generate late fees for overdue installments
    # ------------------------------------------------------------------

    @api.model
    def _cron_generate_late_fees(self):
        LateFeeModel = self.env['late.fee.model']
        today = fields.Date.context_today(self)

        companies = self.env['res.company'].sudo().search(
            [('late_fee_enabled', '=', True)])
        for company in companies:
            default_model = LateFeeModel.sudo()._get_default(company)

            # Step 1: auto-waive stale drafts (paid/exempted since generated)
            stale_drafts = self.sudo().search([
                ('company_id', '=', company.id), ('state', '=', 'draft'),
            ])
            for fee in stale_drafts:
                if (fee.invoice_line_id.reconciled
                        or fee.move_id.late_fee_exempt
                        or fee.partner_id.late_fee_exempt):
                    fee.write({
                        'state': 'waived',
                        'waive_reason': _(
                            'Auto-waived: installment paid or exempted '
                            'before review.'),
                    })

            # Step 2: find eligible overdue installments (per-installment)
            candidate_lines = self.env['account.move.line'].sudo().search([
                ('company_id', '=', company.id),
                ('account_type', '=', 'asset_receivable'),
                ('display_type', '=', 'payment_term'),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('date_maturity', '<', today),
                ('move_id.move_type', '=', 'out_invoice'),
            ])
            for line in candidate_lines:
                self.sudo()._generate_for_line(line, default_model, today)

    def _generate_for_line(self, line, default_model, today):
        move = line.move_id
        partner = move.partner_id
        if move.late_fee_exempt or partner.late_fee_exempt:
            return

        model = move.late_fee_model_id or default_model
        if not model:
            return

        overdue_days = (today - line.date_maturity).days
        if overdue_days < model.grace_period_days:
            return

        period_index = self._compute_period_index(line.date_maturity, model, today)
        if period_index < 1:
            return

        if model.recurrence == 'once':
            target_period_index = 1
        else:
            target_period_index = period_index
            if model.max_occurrences:
                target_period_index = min(target_period_index, model.max_occurrences)
                already_charged = self.search_count([
                    ('invoice_line_id', '=', line.id),
                    ('state', '!=', 'waived'),
                ])
                if already_charged >= model.max_occurrences:
                    return

        if self.search_count([
            ('invoice_line_id', '=', line.id),
            ('period_index', '=', target_period_index),
        ]):
            return

        if line.currency_id != line.company_currency_id:
            base_amount = line.amount_residual_currency
        else:
            base_amount = line.amount_residual
        base_amount = abs(base_amount)

        if model.computation_type == 'percentage':
            fee_amount = line.currency_id.round(
                base_amount * model.percentage / 100.0)
        else:
            fee_amount = model.fixed_amount

        if fee_amount <= 0:
            return

        try:
            with self.env.cr.savepoint():
                self.create({
                    'invoice_line_id': line.id,
                    'late_fee_model_id': model.id,
                    'period_index': target_period_index,
                    'computation_date': today,
                    'overdue_amount': base_amount,
                    'overdue_days': overdue_days,
                    'computation_type': model.computation_type,
                    'rate_applied': model.percentage,
                    'fixed_amount_applied': model.fixed_amount,
                    'interval_type': model.interval_type,
                    'application_mode': model.application_mode,
                    'fee_amount': fee_amount,
                    'state': 'draft',
                })
        except psycopg2.IntegrityError:
            pass

    @api.model
    def _compute_period_index(self, due_date, model, today):
        step_kwargs = {
            'day': {'days': model.interval_number},
            'week': {'weeks': model.interval_number},
            'month': {'months': model.interval_number},
        }[model.interval_type]
        cursor = due_date + relativedelta(days=model.grace_period_days)
        period_index = 0
        while cursor <= today:
            period_index += 1
            cursor += relativedelta(**step_kwargs)
        return period_index

    # ------------------------------------------------------------------
    # Confirm / waive
    # ------------------------------------------------------------------

    def action_confirm(self):
        for fee in self.filtered(lambda f: f.state == 'draft'):
            if (fee.invoice_line_id.reconciled
                    or fee.move_id.late_fee_exempt
                    or fee.partner_id.late_fee_exempt):
                fee.write({
                    'state': 'waived',
                    'waive_reason': _(
                        'Installment paid or exempted before confirmation.'),
                })
                continue

            try:
                with self.env.cr.savepoint():
                    if fee.application_mode == 'same_invoice':
                        fee._apply_same_invoice()
                    else:
                        fee._apply_new_invoice()
            except UserError as e:
                fee.write({'state': 'error', 'error_message': str(e)})
                fee.message_post(body=_('Confirmation failed: %s', e))
                continue

            fee.write({
                'state': 'confirmed',
                'confirmed_by': self.env.user.id,
                'confirmed_date': fields.Datetime.now(),
            })
            try:
                fee._send_notification_email()
            except Exception as e:  # best-effort: never block on email issues
                fee.message_post(body=_(
                    'Late fee applied, but the notification email could '
                    'not be sent: %s', e))

    def action_waive(self):
        for fee in self.filtered(lambda f: f.state == 'draft'):
            fee.write({
                'state': 'waived',
                'waived_by': self.env.user.id,
                'waived_date': fields.Datetime.now(),
            })

    def _apply_new_invoice(self):
        self.ensure_one()
        model = self.late_fee_model_id
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_origin': self.move_id.name,
            'ref': _('Late Fee - %s', self.move_id.name),
            'journal_id': (model.late_fee_journal_id or self.move_id.journal_id).id,
            'invoice_user_id': self.move_id.invoice_user_id.id,
            'narration': self.description,
            'invoice_line_ids': [Command.create({
                'product_id': model.late_fee_product_id.id,
                'name': self.description,
                'quantity': 1,
                'price_unit': self.fee_amount,
            })],
        })
        move.action_post()
        self.write({
            'fee_move_id': move.id,
            'fee_invoice_line_id': move.invoice_line_ids[:1].id,
        })

    def _apply_same_invoice(self):
        self.ensure_one()
        move = self.move_id
        model = self.late_fee_model_id

        if move.is_move_sent:
            self.error_message = _(
                'Invoice %s was already sent to the customer; created a '
                'separate late fee invoice instead of editing it.',
                move.name)
            self._apply_new_invoice()
            return

        try:
            with self.env.cr.savepoint():
                move.button_draft()
                move.write({'invoice_line_ids': [Command.create({
                    'product_id': model.late_fee_product_id.id,
                    'name': self.description,
                    'quantity': 1,
                    'price_unit': self.fee_amount,
                })]})
                move.action_post()
        except UserError as e:
            self.error_message = _(
                'Could not add the fee to invoice %(invoice)s '
                '(%(reason)s); created a separate late fee invoice '
                'instead.', invoice=move.name, reason=str(e))
            self._apply_new_invoice()
            return

        fee_line = move.invoice_line_ids.filtered(
            lambda l: l.product_id == model.late_fee_product_id
        ).sorted('id')[-1:]
        self.write({
            'fee_move_id': move.id,
            'fee_invoice_line_id': fee_line.id,
        })

    def _send_notification_email(self):
        self.ensure_one()
        if not self.late_fee_model_id.send_notification_email:
            return
        template = self.late_fee_model_id.mail_template_id or self.env.ref(
            'account_late_fee.mail_template_late_fee_notice',
            raise_if_not_found=False)
        if not template:
            return
        cc_list = []
        if self.company_id.late_fee_notification_email:
            cc_list.append(self.company_id.late_fee_notification_email)
        if self.move_id.invoice_user_id.email:
            cc_list.append(self.move_id.invoice_user_id.email)
        email_values = {'email_cc': ','.join(cc_list)} if cc_list else {}
        template.send_mail(self.id, force_send=True, email_values=email_values)
        self.mail_sent = True
