from collections import defaultdict
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import RedirectWarning, UserError

SECTIONS = ('bill', 'credit', 'other')


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    remittance_registration_ids = fields.One2many(
        'enterprise.remittance.registration', 'payment_id', string="Remittance Records", readonly=True)
    remittance_registration_id = fields.Many2one(
        'enterprise.remittance.registration', string="Remittance Record",
        compute='_compute_remittance_registration_id', search='_search_remittance_registration_id')
    remittance_has_snapshot = fields.Boolean(compute='_compute_remittance_registration_id')
    remittance_allocation_ids = fields.One2many(
        related='remittance_registration_id.allocation_ids', string="Payment Allocation")
    remittance_reconciliation_ids = fields.One2many(
        related='remittance_registration_id.reconciliation_ids', string="Reconciliation Trail")
    remittance_diagnostic = fields.Text(related='remittance_registration_id.diagnostic', string="Allocation Diagnostic")
    remittance_payment_changed = fields.Boolean(related='remittance_registration_id.payment_changed')
    remittance_debug_snapshot = fields.Text(
        related='remittance_registration_id.debug_snapshot', string="Debug Snapshot",
        groups='account.group_account_manager')
    remittance_note = fields.Text(
        string="Remittance Note",
        help="Optional message printed on the remittance slip (for example a reference for the vendor).")

    @api.depends('remittance_registration_ids')
    def _compute_remittance_registration_id(self):
        for payment in self:
            registration = payment.remittance_registration_ids[:1]
            payment.remittance_registration_id = registration
            payment.remittance_has_snapshot = bool(registration)

    def _search_remittance_registration_id(self, operator, value):
        return [('remittance_registration_ids', operator, value)]

    # ------------------------------------------------------------------
    # State follows the payment; controlled reset / cancel / delete
    # ------------------------------------------------------------------
    def write(self, vals):
        result = super().write(vals)
        if 'state' in vals:
            self.remittance_registration_ids._remittance_sync_state()
        return result

    def _remittance_guard(self, operation):
        """Refuse to reset / cancel / delete a payment whose registration still owns bill/credit
        offsets, unless the caller states what to do with them.

        The decision comes from the remittance wizard (or trusted code) through the context key
        ``remittance_offset_decision`` = 'keep' | 'reverse'. Without it the user is sent to the wizard.
        Payments without owned offsets, and payments never tracked, are not affected.
        """
        if self.env.context.get('remittance_offset_decision') in ('keep', 'reverse'):
            return
        # sudo: read-only lookup of our own audit records, so users without access to them are not blocked by an AccessError.
        registrations = self.sudo().remittance_registration_ids.filtered(
            lambda registration: registration.active_offset_count)
        if not registrations:
            return
        raise RedirectWarning(
            _("This payment settled bills and credits together in one registration, which created "
              "bill/credit offsets. Decide what to do with those offsets before continuing."),
            registrations.with_env(self.env)._remittance_cancel_wizard_action(operation),
            _("Review Offsets"),
        )

    def action_draft(self):
        self._remittance_guard('draft')
        registrations = self.remittance_registration_ids
        result = super(AccountPayment, self.with_context(remittance_removal_via='payment_draft')).action_draft()
        self._remittance_after_operation('draft', registrations)
        return result

    def action_cancel(self):
        self._remittance_guard('cancel')
        registrations = self.remittance_registration_ids
        result = super(AccountPayment, self.with_context(remittance_removal_via='payment_cancel')).action_cancel()
        self._remittance_after_operation('cancel', registrations)
        return result

    def unlink(self):
        self._remittance_guard('delete')
        registrations = self.remittance_registration_ids
        result = super(AccountPayment, self.with_context(remittance_removal_via='payment_delete')).unlink()
        registrations.invalidate_recordset(['payment_id'])
        self._remittance_after_operation('delete', registrations)
        return result

    def _remittance_after_operation(self, operation, registrations):
        """Log the event on the remittance record and apply the offset decision, if any."""
        if not registrations:
            return
        registrations = registrations.exists()
        registrations._remittance_sync_state()
        if operation == 'delete':
            # sudo: audit state column, see _remittance_sync_state
            registrations.sudo().write({'state': 'deleted'})
        decision = self.env.context.get('remittance_offset_decision')
        reason = self.env.context.get('remittance_reason')
        for registration in registrations:
            reversed_rows, retained = None, None
            if not registration._remittance_active_offsets():
                outcome = 'not_applicable'
            elif decision == 'reverse':
                reversed_rows, retained = registration._remittance_reverse_offsets('after_' + operation)
                if reversed_rows and retained:
                    outcome = 'partial'
                elif reversed_rows:
                    outcome = 'reversed'
                else:
                    outcome = 'kept'
            else:
                outcome = 'kept'
            registration._remittance_record_event(
                operation, outcome, reason, reversed_rows=reversed_rows, retained=retained)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_print_remittance_slip(self):
        return self.env.ref('enterprise_remittance_management.action_report_remittance_slip').report_action(self)

    def action_send_remittance(self):
        self.ensure_one()
        template = self.env.ref('enterprise_remittance_management.mail_template_remittance', raise_if_not_found=False)
        if not template:
            raise UserError(_("The remittance email template is missing."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Send Remittance"),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_model': 'account.payment',
                'default_res_ids': self.ids,
                'default_template_id': template.id,
                'default_composition_mode': 'comment',
                'default_email_layout_xmlid': 'mail.mail_notification_light',
                'mail_post_autofollow': True,
            },
        }

    # ------------------------------------------------------------------
    # Remittance slip data (single source for the PDF)
    # ------------------------------------------------------------------
    def _remittance_slip_data(self):
        """Everything the remittance slip prints, as plain values.

        Figures come from the immutable allocation lines. A payment without a snapshot gets a clearly
        labelled fallback built from native reconciliation data, and only when that data fully explains
        the payment; otherwise no table is printed rather than a misleading one.
        """
        self.ensure_one()
        registration = self.remittance_registration_id
        status = {'draft': 'draft', 'canceled': 'cancelled', 'rejected': 'cancelled'}.get(self.state, False)
        # The native memo lists every document reference, which is unreadable on a long payment; the tables already do that.
        memo = self.memo or ''
        data = {
            'payment': self,
            'registration': registration,
            'source': 'snapshot' if registration else 'legacy',
            'legacy_notice': False,
            'currency': self.currency_id,
            'payment_type': self.payment_type,
            'status_banner': status,
            'memo': memo if len(memo) <= 160 else memo[:157].rstrip(' ,') + '...',
            'rows': {section: [] for section in SECTIONS},
            'totals': {},
            'multi_currency': False,
            'writeoff': 0.0,
            'unallocated': 0.0,
            'has_remaining': False,
            'show_note': self.company_id.remittance_show_note and bool(self.remittance_note),
        }
        rows = self._remittance_snapshot_rows(registration) if registration else self._remittance_legacy_rows(data)
        for row in rows:
            data['rows'][row['section']].append(row)
        for section in SECTIONS:
            data['rows'][section].sort(key=lambda row: (row['date'] or date.max, row['reference'] or '', row['id']))
        all_rows = [row for section in SECTIONS for row in data['rows'][section]]
        data['has_remaining'] = any(row['has_remaining'] for row in all_rows)
        data['multi_currency'] = any(row['currency'] != self.currency_id for row in all_rows)
        data['totals'] = {
            'bills': self._remittance_totals_by_currency(data['rows']['bill']),
            'credits': self._remittance_totals_by_currency(data['rows']['credit']),
            'other': self._remittance_totals_by_currency(data['rows']['other']),
        }
        if registration:
            data['writeoff'] = registration.writeoff_amount
            data['unallocated'] = registration.unallocated_amount
            data['net'] = registration.net_amount
        else:
            data['net'] = self.amount if self.payment_type == 'outbound' else -self.amount
        return data

    @staticmethod
    def _remittance_totals_by_currency(rows):
        totals = defaultdict(float)
        for row in rows:
            totals[row['currency']] += row['applied']
        return [(currency, currency.round(amount)) for currency, amount in totals.items()]

    def _remittance_snapshot_rows(self, registration):
        return [{
            'id': line.id,
            'section': line.document_type,
            'reference': line.display_reference,
            'number': line.document_name if line.document_ref else False,
            'date': line.document_date,
            'due_date': line.due_date,
            'currency': line.currency_id,
            'original': line.original_amount,
            'due_before': line.amount_due_before,
            'applied': line.amount_applied,
            'remaining': line.amount_remaining,
            'has_remaining': line.has_remaining,
            'paid_in_payment_currency': line.payment_amount if line.currency_id != registration.currency_id else False,
            'note': line.previous_settlement_note,
        } for line in registration.allocation_ids]

    def _remittance_legacy_rows(self, data):
        """Fallback for payments created without the allocation snapshot.

        Uses the native reconciliation only when it fully explains the payment amount. It reflects the
        CURRENT state of the documents, which is not necessarily what was selected when the payment was
        made (offsets that preceded the payment may hide documents), so the slip says so.
        """
        self.ensure_one()
        data['legacy_notice'] = _(
            "This payment was recorded before allocation tracking was enabled. The documents below are "
            "rebuilt from the current accounting reconciliation and may not show the complete original "
            "selection. Balances before payment are not available.")
        if not self.move_id or self.state == 'draft':
            data['source'] = 'unavailable'
            data['legacy_notice'] = _(
                "This payment has no allocation record and no posted accounting entry, so the "
                "documents it settled cannot be shown.")
            return []
        rows, applied_total = [], 0.0
        payable_types = self._get_valid_payment_account_types()
        payment_lines = self.move_id.line_ids.filtered(lambda line: line.account_type in payable_types)
        partials = payment_lines.matched_debit_ids | payment_lines.matched_credit_ids
        by_move = defaultdict(lambda: {'applied': 0.0, 'currency': False})
        for partial in partials:
            for line, side in ((partial.debit_move_id, 'debit'), (partial.credit_move_id, 'credit')):
                # Only vendor documents count. Anything else (exchange difference entries, journal
                # entries) is left out on purpose so it shows up as an unexplained difference below.
                if line in payment_lines or line.move_id.move_type not in DOCUMENT_TYPE_TO_SECTION:
                    continue
                figures = by_move[line.move_id]
                figures['currency'] = line.currency_id or line.company_currency_id
                sign = 1 if side == 'credit' else -1
                own = partial.credit_amount_currency if side == 'credit' else partial.debit_amount_currency
                figures['applied'] += sign * own
                other = partial.debit_amount_currency if side == 'credit' else partial.credit_amount_currency
                applied_total += sign * other
        settled = sum(payment_lines.mapped('amount_currency'))
        if not by_move or not self.currency_id.is_zero(settled - applied_total):
            data['source'] = 'unavailable'
            data['legacy_notice'] = _(
                "This payment was recorded before allocation tracking was enabled and its current "
                "reconciliation does not fully explain the payment amount, so the detail of the "
                "documents it settled cannot be shown reliably.")
            return []
        for move, figures in by_move.items():
            currency = figures['currency']
            rows.append({
                'id': move.id,
                'section': DOCUMENT_TYPE_TO_SECTION.get(move.move_type, 'other'),
                'reference': move.ref or move.name,
                'number': move.name if move.ref else False,
                'date': move.invoice_date or move.date,
                'due_date': move.invoice_date_due,
                'currency': currency,
                'original': currency.round(-sum(move.line_ids.filtered(
                    lambda line: line.account_type in payable_types).mapped('amount_currency'))),
                'due_before': False,
                'applied': currency.round(figures['applied']),
                'remaining': False,
                'has_remaining': False,
                'paid_in_payment_currency': False,
                'note': False,
            })
        return rows


DOCUMENT_TYPE_TO_SECTION = {
    'in_invoice': 'bill',
    'in_receipt': 'bill',
    'in_refund': 'credit',
}
