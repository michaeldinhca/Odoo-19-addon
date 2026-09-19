import logging

from markupsafe import Markup, escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

_logger = logging.getLogger(__name__)

# Columns describing what happened at registration time. They can never be
# changed once the record exists (see write() below). Only the workflow and
# audit columns (state, cancel_*) and the payment link (cleared when the
# payment is deleted) may change afterwards.
SNAPSHOT_FIELDS = frozenset({
    'name', 'company_id', 'partner_id', 'payment_type', 'payment_date', 'currency_id', 'memo',
    'payment_amount', 'net_amount', 'settled_amount', 'writeoff_amount', 'unallocated_amount',
    'run_ref', 'origin', 'debug_snapshot', 'diagnostic', 'has_diagnostic',
})


class RemittanceRegistration(models.Model):
    """One record per payment created by the Register Payment wizard.

    It is the anchor of the audit trail: it survives the deletion of the payment
    (payment_id is cleared, every other column is a stored copy), owns the
    immutable allocation lines and the reconciliation ownership trail, and keeps
    the chatter history of reset / cancel / delete decisions.
    """
    _name = 'enterprise.remittance.registration'
    _description = 'Remittance Payment Registration'
    _inherit = ['mail.thread']
    _order = 'payment_date desc, id desc'
    # Read-only users may add notes; system events are posted through message_post().
    _mail_post_access = 'read'

    _payment_uniq = models.Constraint(
        'unique(payment_id)',
        "A payment can only have one remittance registration record.",
    )

    # ------------------------------------------------------------------
    # Identity and link to the payment
    # ------------------------------------------------------------------
    name = fields.Char(
        string="Reference", required=True, readonly=True, copy=False, index=True,
        help="Payment reference at the time of registration. Kept even if the payment is deleted.")
    company_id = fields.Many2one(
        'res.company', required=True, readonly=True, index=True, ondelete='restrict')
    payment_id = fields.Many2one(
        'account.payment', string="Payment", readonly=True, ondelete='set null', copy=False,
        help="The payment this record describes. Empty once the payment has been deleted; "
             "every figure on this record is a stored copy and stays readable.")
    payment_state = fields.Selection(related='payment_id.state', string="Payment Status")
    run_ref = fields.Char(
        string="Registration Run", readonly=True, index=True, copy=False,
        help="Shared by every payment created by one execution of the Register Payment wizard. "
             "Lets you see which payments were produced together (for example one per vendor).")
    origin = fields.Selection(
        [('registered', "Payment Registration"), ('migrated', "Migrated from Legacy Data")],
        default='registered', required=True, readonly=True,
        help="Whether the snapshot was captured live by the Register Payment wizard or imported "
             "from legacy data. Imported records cannot prove ownership of bill/credit offsets.")

    # ------------------------------------------------------------------
    # Payment summary (stored copy)
    # ------------------------------------------------------------------
    partner_id = fields.Many2one(
        'res.partner', string="Vendor", readonly=True, index=True, ondelete='restrict')
    payment_type = fields.Selection(
        [('outbound', "Sent to vendor"), ('inbound', "Received from vendor")], readonly=True)
    payment_date = fields.Date(readonly=True, index=True)
    memo = fields.Char(readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string="Payment Currency", readonly=True,
        help="Currency of the payment.")
    payment_amount = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="Payment amount as recorded on the payment (always positive).")
    net_amount = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="Signed net payment in the payment currency. Positive: paid to the vendor. "
             "Negative: received from the vendor.")
    settled_amount = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="Signed amount the payment settled against documents (payable side of the payment "
             "entry). Differs from the net payment only when a write-off or discount was posted.")
    writeoff_amount = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="Settled amount minus net payment: the difference posted to a write-off or discount account.")
    unallocated_amount = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="Part of the payment that was not applied to any document (for example an overpayment "
             "left open on the vendor account).")

    # ------------------------------------------------------------------
    # Workflow and audit
    # ------------------------------------------------------------------
    state = fields.Selection(
        [('active', "Posted"), ('draft', "Reset to Draft"), ('cancelled', "Cancelled"), ('deleted', "Payment Deleted")],
        default='active', required=True, readonly=True, tracking=True, index=True,
        help="Follows the payment. Deleted means the payment record no longer exists but this history is kept.")
    cancel_operation = fields.Selection(
        [('draft', "Reset to Draft"), ('cancel', "Cancel"), ('delete', "Delete"), ('offsets_only', "Reverse Retained Offsets")],
        string="Last Operation", readonly=True)
    cancel_outcome = fields.Selection(
        [('not_applicable', "No bill/credit offsets involved"),
         ('kept', "Bill/credit offsets kept"),
         ('reversed', "Bill/credit offsets reversed"),
         ('partial', "Some offsets reversed, others kept")],
        string="Offset Outcome", readonly=True, tracking=True)
    cancel_user_id = fields.Many2one('res.users', string="Decided By", readonly=True)
    cancel_date = fields.Datetime(string="Decision Date", readonly=True)
    cancel_reason = fields.Text(string="Reason", readonly=True)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    diagnostic = fields.Text(
        readonly=True,
        help="Explicit description of any figure that could not be reconciled when the snapshot was "
             "taken. Empty when every line ties to the payment.")
    has_diagnostic = fields.Boolean(readonly=True, index=True)
    debug_snapshot = fields.Text(
        string="Debug Snapshot", readonly=True, groups='account.group_account_manager',
        help="Human-readable capture in the legacy Vendor ID|Move ID|Amount format (amount = due "
             "before payment, credits negative). For cross-checking only.")

    # ------------------------------------------------------------------
    # Children
    # ------------------------------------------------------------------
    allocation_ids = fields.One2many(
        'enterprise.remittance.allocation', 'registration_id', string="Allocations", readonly=True)
    reconciliation_ids = fields.One2many(
        'enterprise.remittance.reconciliation', 'registration_id', string="Reconciliation Trail", readonly=True)
    allocation_count = fields.Integer(compute='_compute_counts')
    active_offset_count = fields.Integer(
        compute='_compute_counts',
        help="Bill/credit offsets created by this registration that still exist.")
    payment_changed = fields.Boolean(
        compute='_compute_payment_changed',
        help="The payment was edited after registration; the snapshot keeps the original figures.")

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('allocation_ids', 'reconciliation_ids.partial_id', 'reconciliation_ids.kind')
    def _compute_counts(self):
        for registration in self:
            registration.allocation_count = len(registration.allocation_ids)
            registration.active_offset_count = len(registration._remittance_active_offsets())

    @api.depends('payment_id.amount', 'payment_id.currency_id', 'payment_id.partner_id',
                 'payment_amount', 'currency_id', 'partner_id')
    def _compute_payment_changed(self):
        for registration in self:
            payment = registration.payment_id
            registration.payment_changed = bool(payment) and (
                payment.currency_id != registration.currency_id
                or payment.partner_id != registration.partner_id
                or (registration.currency_id and not registration.currency_id.is_zero(
                    payment.amount - registration.payment_amount))
            )

    def _remittance_active_offsets(self):
        return self.reconciliation_ids.filtered(lambda row: row.kind == 'offset' and row.partial_id)

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------
    def write(self, vals):
        locked = SNAPSHOT_FIELDS.intersection(vals)
        if locked:
            raise UserError(_(
                "The remittance snapshot is immutable. These fields cannot be changed after creation: %s",
                ", ".join(sorted(self._fields[name].string for name in locked)),
            ))
        if 'payment_id' in vals and vals['payment_id']:
            raise UserError(_("The payment link of a remittance record cannot be reassigned."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_audit_history(self):
        raise UserError(_(
            "Remittance records are audit history and cannot be deleted. "
            "They stay readable even after the payment they describe is deleted."))

    # ------------------------------------------------------------------
    # State follows the payment
    # ------------------------------------------------------------------
    def _remittance_sync_state(self):
        """Align the workflow state with the payment (no-op once the payment is deleted)."""
        mapping = {'draft': 'draft', 'canceled': 'cancelled', 'rejected': 'cancelled'}
        for registration in self.filtered('payment_id'):
            new_state = mapping.get(registration.payment_id.state, 'active')
            if registration.state != new_state:
                # sudo: audit records are read-only for end users; only this controlled sync may change state.
                registration.sudo().write({'state': new_state})

    # ------------------------------------------------------------------
    # Offset reversal (Option B)
    # ------------------------------------------------------------------
    def _remittance_reverse_offsets(self, operation):
        """Reverse the bill/credit offsets that are provably owned by these registrations and safe to reverse.

        Every offset is re-checked (see enterprise.remittance.reconciliation._reversal_check). Whatever is
        not eligible is left untouched, with the reason returned to the caller.

        :return: (reversed rows, [(retained row, reason), ...])
        """
        reversed_rows = self.env['enterprise.remittance.reconciliation']
        partials = self.env['account.partial.reconcile']
        retained = []
        for row in self._remittance_active_offsets():
            eligible, message = row.with_context(remittance_operation=operation)._reversal_check()
            if eligible:
                reversed_rows |= row
                partials |= row.partial_id
            else:
                retained.append((row, message))
        if partials:
            # Runs with the user's own rights: no sudo, native unlink reverses exchange/cash-basis entries.
            partials.with_context(remittance_removal_via='reversed_by_user').unlink()
            reversed_rows.invalidate_recordset(['partial_id'])
        return reversed_rows, retained

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------
    def _remittance_record_event(self, operation, outcome, reason=None, reversed_rows=None, retained=None):
        """Store who/when/why/outcome and log the event in the chatter (registration and payment)."""
        operation_label = dict(self._fields['cancel_operation'].selection)[operation]
        outcome_label = dict(self._fields['cancel_outcome'].selection)[outcome]
        reason = (reason or '').strip()
        for registration in self:
            registration.sudo().write({  # sudo: audit columns are not writable by end users
                'cancel_operation': operation,
                'cancel_outcome': outcome,
                'cancel_user_id': self.env.user.id,
                'cancel_date': fields.Datetime.now(),
                'cancel_reason': reason or False,
            })
            body = Markup("<p><b>%s</b> - %s</p>") % (operation_label, outcome_label)
            if reason:
                body += Markup("<p>%s: %s</p>") % (_("Reason"), reason)
            details = []
            for row in (reversed_rows or registration.reconciliation_ids.browse()):
                if row.registration_id == registration:
                    details.append(Markup("<li>%s: %s</li>") % (_("Reversed"), row._remittance_describe()))
            for row, message in (retained or []):
                if row.registration_id == registration:
                    details.append(Markup("<li>%s: %s (%s)</li>") % (_("Kept"), row._remittance_describe(), message))
            if not details and outcome == 'kept':
                for row in registration._remittance_active_offsets():
                    details.append(Markup("<li>%s: %s</li>") % (_("Kept"), row._remittance_describe()))
            if details:
                body += Markup("<ul>%s</ul>") % Markup("").join(details)
            registration.message_post(body=body, subtype_xmlid='mail.mt_note')
            if registration.payment_id:
                registration.payment_id.message_post(
                    body=Markup("<p>%s <b>%s</b> - %s</p>") % (
                        _("Remittance record"), escape(registration.name), outcome_label),
                    subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _remittance_cancel_wizard_action(self, operation):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Payment Bill/Credit Offsets"),
            'res_model': 'enterprise.remittance.cancel.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'dialog_size': 'extra-large',
                'default_operation': operation,
                'default_registration_ids': [Command.set(self.ids)],
                'default_payment_ids': [Command.set(self.payment_id.ids)],
            },
        }

    def action_reverse_retained_offsets(self):
        self.ensure_one()
        return self._remittance_cancel_wizard_action('offsets_only')

    def action_open_payment(self):
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("The payment of this remittance record no longer exists."))
        return self.payment_id._get_records_action()

    def action_print_remittance_slip(self):
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("The payment no longer exists, so its remittance slip cannot be printed."))
        return self.payment_id.action_print_remittance_slip()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _remittance_format_net(self):
        """Wording for the net payment, direction aware (used in messages and emails)."""
        self.ensure_one()
        amount = format_amount(self.env, abs(self.net_amount), self.currency_id)
        if self.payment_type == 'inbound':
            return _("%s received from the vendor", amount)
        return _("%s paid to the vendor", amount)
