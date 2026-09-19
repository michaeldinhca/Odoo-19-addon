from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import format_amount


class RemittanceCancelWizard(models.TransientModel):
    """Controlled reset / cancel / delete of a payment that settled bills and credits together.

    Shows the payment, the vendor, the amount, the source documents and every reconciliation link
    that the registration owns, then records the user's decision:

    * Keep (safe default): the payment is reset/cancelled/deleted and the bill/credit offsets stay.
    * Reverse: only the offsets that are provably owned by the registration AND still safe to reverse
      are reversed. Anything else is left in place, with the reason shown.

    Nothing is ever reversed silently: reversal needs an explicit choice, a reason, and an Accounting
    Administrator or Accountant.
    """
    _name = 'enterprise.remittance.cancel.wizard'
    _description = 'Payment Bill/Credit Offsets Decision'

    operation = fields.Selection(
        [('draft', "Reset to Draft"), ('cancel', "Cancel"), ('delete', "Delete"),
         ('offsets_only', "Reverse Retained Offsets")],
        required=True, readonly=True)
    registration_ids = fields.Many2many(
        'enterprise.remittance.registration', 'erm_cancel_wizard_registration_rel', 'wizard_id', 'registration_id',
        string="Remittance Records", readonly=True)
    payment_ids = fields.Many2many(
        'account.payment', 'erm_cancel_wizard_payment_rel', 'wizard_id', 'payment_id',
        string="Payments", readonly=True)
    allocation_ids = fields.Many2many(
        'enterprise.remittance.allocation', compute='_compute_display_lines', string="Source Bills and Credits")
    reconciliation_ids = fields.Many2many(
        'enterprise.remittance.reconciliation', compute='_compute_display_lines', string="Offset Rows")
    offsets_html = fields.Html(
        compute='_compute_offsets_html', sanitize=False, string="Reconciliation Links",
        help="Each bill/credit offset of the registration and whether it can be reversed for this operation.")

    outcome = fields.Selection(
        [('keep', "Keep the bill/credit offsets (recommended)"),
         ('reverse', "Reverse the offsets that can be reversed safely")],
        default='keep', required=True)
    reason = fields.Text(required=True, help="Recorded on the remittance record and in the chatter.")

    eligible_count = fields.Integer(compute='_compute_eligibility')
    blocked_count = fields.Integer(compute='_compute_eligibility')
    can_reverse = fields.Boolean(compute='_compute_eligibility')
    reverse_blocker = fields.Char(compute='_compute_eligibility')

    # ------------------------------------------------------------------
    # Rights
    # ------------------------------------------------------------------
    def _user_may_reverse(self):
        """Reversing reconciliations is limited to Accounting Administrators and Accountants."""
        user = self.env.user
        return user.has_group('account.group_account_manager') or user.has_group('account.group_account_user')

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('registration_ids')
    def _compute_display_lines(self):
        for wizard in self:
            wizard.allocation_ids = wizard.registration_ids.allocation_ids
            wizard.reconciliation_ids = wizard.registration_ids.reconciliation_ids.filtered(
                lambda row: row.kind == 'offset')

    @api.depends('registration_ids', 'operation')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_offsets_html(self):
        """Rendered on the server with the explicit operation: a client-side context is not reliable here."""
        for wizard in self:
            rows = wizard.registration_ids.reconciliation_ids.filtered(lambda row: row.kind == 'offset').sorted('id')
            if not rows:
                wizard.offsets_html = Markup('<p class="text-muted mb-0">%s</p>') % _(
                    "This payment has no bill/credit offset.")
                continue
            body = Markup('')
            for row in rows:
                note = Markup('')
                if not row.partial_id:
                    status, css = _("Already removed"), 'text-muted'
                else:
                    eligible, message = row._reversal_check(wizard.operation)
                    status, css = (_("Can be reversed"), 'text-success') if eligible else (
                        _("Cannot be reversed"), 'text-warning')
                    if message:
                        note = Markup('<br/><small>%s</small>') % message
                body += Markup('<tr><td>%s</td><td>%s</td><td class="text-end">%s</td>'
                               '<td class="%s"><strong>%s</strong>%s</td></tr>') % (
                    row.debit_document or '', row.credit_document or '',
                    format_amount(self.env, row.amount, row.company_currency_id), css, status, note)
            wizard.offsets_html = Markup(
                '<table class="table table-sm mb-0"><thead><tr><th>%s</th><th>%s</th>'
                '<th class="text-end">%s</th><th>%s</th></tr></thead><tbody>%s</tbody></table>') % (
                _("Debit entry"), _("Credit entry"), _("Amount"), _("Reversal"), body)

    @api.depends('registration_ids', 'operation')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_eligibility(self):
        may_reverse = self._user_may_reverse()
        for wizard in self:
            rows = wizard.registration_ids._remittance_active_offsets()
            statuses = [row._reversal_check(wizard.operation)[0] for row in rows]
            wizard.eligible_count = sum(statuses)
            wizard.blocked_count = len(statuses) - sum(statuses)
            wizard.can_reverse = may_reverse and bool(wizard.eligible_count)
            if not may_reverse:
                wizard.reverse_blocker = _(
                    "Reversing reconciliations requires the Accounting Administrator or Accountant access level.")
            elif not wizard.eligible_count:
                wizard.reverse_blocker = _("None of the offsets can be reversed automatically. See the reasons above.")
            else:
                wizard.reverse_blocker = False

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        if not (self.reason or '').strip():
            raise UserError(_("Please give a reason: it is recorded for audit."))
        outcome = 'reverse' if self.operation == 'offsets_only' else self.outcome
        if outcome == 'reverse':
            if not self._user_may_reverse():
                raise AccessError(_(
                    "Reversing reconciliations requires the Accounting Administrator or Accountant access level."))
            if not self.eligible_count:
                raise UserError(self.reverse_blocker or _("Nothing can be reversed automatically."))
        if self.operation == 'delete' and self.payment_ids.filtered(lambda payment: payment.state != 'draft'):
            raise UserError(_("A payment must be reset to draft before it can be deleted."))
        context = {'remittance_offset_decision': outcome, 'remittance_reason': self.reason.strip()}
        if self.operation == 'offsets_only':
            self._reverse_retained_offsets(context)
        else:
            payments = self.payment_ids.with_context(**context)
            if self.operation == 'draft':
                payments.action_draft()
            elif self.operation == 'cancel':
                payments.action_cancel()
            else:
                payments.unlink()
                return {
                    'type': 'ir.actions.act_window',
                    'name': _("Payments"),
                    'res_model': 'account.payment',
                    'view_mode': 'list,form',
                    'views': [(False, 'list'), (False, 'form')],
                    'target': 'main',
                }
        # The wizard may have been opened from an error dialog, so the form underneath does not refresh by itself.
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def _reverse_retained_offsets(self, context):
        for registration in self.registration_ids.with_context(**context):
            reversed_rows, retained = registration._remittance_reverse_offsets('offsets_only')
            if reversed_rows and retained:
                outcome = 'partial'
            elif reversed_rows:
                outcome = 'reversed'
            else:
                outcome = 'kept'
            registration._remittance_record_event(
                'offsets_only', outcome, context['remittance_reason'],
                reversed_rows=reversed_rows, retained=retained)
