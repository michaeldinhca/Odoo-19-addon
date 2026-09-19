from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RemittanceAllocation(models.Model):
    """One immutable line per source document (bill or credit) settled by a payment registration.

    All figures are stored copies taken at registration time: the amount due before payment is read
    BEFORE the native reconciliation, the applied amounts come from the partial reconciles that the
    registration actually created. Nothing here is ever recomputed from live residuals.

    Sign convention (document currency): bills are positive, credits are negative.
    """
    _name = 'enterprise.remittance.allocation'
    _description = 'Remittance Allocation Line'
    _order = 'registration_id, document_date, document_ref, document_name, id'

    _registration_move_uniq = models.Constraint(
        'unique(registration_id, move_id)',
        "A document can only appear once per payment registration.",
    )

    registration_id = fields.Many2one(
        'enterprise.remittance.registration', string="Registration", required=True, readonly=True,
        ondelete='cascade')
    company_id = fields.Many2one(
        related='registration_id.company_id', store=True, index=True, readonly=True)
    payment_id = fields.Many2one(
        related='registration_id.payment_id', string="Payment", readonly=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string="Company Currency", readonly=True)
    payment_currency_id = fields.Many2one(
        related='registration_id.currency_id', string="Payment Currency", store=True, readonly=True)

    # ------------------------------------------------------------------
    # Document identity (stored copy, readable even if the document is gone)
    # ------------------------------------------------------------------
    vendor_id = fields.Many2one(
        'res.partner', string="Vendor", readonly=True, index=True, ondelete='restrict',
        help="Commercial partner of the document at registration time.")
    move_id = fields.Many2one(
        'account.move', string="Document", readonly=True, index=True, ondelete='set null')
    document_name = fields.Char(string="Number", readonly=True)
    document_ref = fields.Char(string="Vendor Reference", readonly=True)
    display_reference = fields.Char(
        string="Bill/Credit Reference", compute='_compute_display_reference',
        help="Vendor reference when there is one, otherwise the Odoo document number.")
    document_type = fields.Selection(
        [('bill', "Vendor Bill"), ('credit', "Vendor Credit"), ('other', "Other Entry")],
        string="Type", readonly=True, required=True)
    document_date = fields.Date(string="Bill/Credit Date", readonly=True)
    due_date = fields.Date(readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string="Document Currency", required=True, readonly=True)

    # ------------------------------------------------------------------
    # Amounts, document currency
    # ------------------------------------------------------------------
    original_amount = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="Original total of the document payable lines. Bills positive, credits negative.")
    previously_settled_amount = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="Original amount minus amount due before payment: what was already settled before this "
             "registration (earlier payments and credit offsets).")
    amount_due_before = fields.Monetary(
        string="Amount Due Before Payment", currency_field='currency_id', readonly=True,
        help="Outstanding amount read from the accounting lines just before this registration reconciled them.")
    payment_applied = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="Part of the amount settled directly by the payment entry.")
    offset_applied = fields.Monetary(
        string="Credit Offset Applied", currency_field='currency_id', readonly=True,
        help="Part of the amount settled by offsetting against another bill or credit selected in the same registration.")
    amount_applied = fields.Monetary(
        string="Applied Amount", currency_field='currency_id', readonly=True,
        help="Total settled by this registration (payment plus offset).")
    amount_remaining = fields.Monetary(
        string="Remaining After Payment", currency_field='currency_id', readonly=True,
        help="Outstanding amount read immediately after the registration reconciled the document.")
    has_remaining = fields.Boolean(compute='_compute_has_remaining')

    # ------------------------------------------------------------------
    # Amounts in the other currencies
    # ------------------------------------------------------------------
    payment_amount = fields.Monetary(
        string="Paid (Payment Currency)", currency_field='payment_currency_id', readonly=True,
        help="Amount of the payment entry attributed to this document, in the payment currency "
             "(document sign). Zero when the document was settled only by offset.")
    applied_amount_company = fields.Monetary(
        string="Applied (Company Currency)", currency_field='company_currency_id', readonly=True,
        help="Applied amount in company currency at the document's own rate. Exchange differences "
             "generated by the reconciliation are recorded separately in the reconciliation trail.")

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------
    split_known = fields.Boolean(
        string="Payment/Offset Split Known", default=True, readonly=True,
        help="False for migrated lines: legacy data does not tell how much was paid versus offset.")
    previous_settlement_note = fields.Char(
        readonly=True,
        help="Explains earlier bill/credit offsets on this document that came from another registration.")
    legacy_source = fields.Char(
        readonly=True, help="Reference of the legacy record this line was migrated from.")
    diagnostic = fields.Char(
        readonly=True, help="Set when the line figures did not tie out at registration time.")

    @api.depends('document_ref', 'document_name')
    def _compute_display_reference(self):
        for line in self:
            line.display_reference = line.document_ref or line.document_name or ''

    @api.depends('amount_remaining', 'currency_id')
    def _compute_has_remaining(self):
        for line in self:
            line.has_remaining = bool(line.currency_id) and not line.currency_id.is_zero(line.amount_remaining)

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------
    def write(self, vals):
        raise UserError(_("Allocation lines are an immutable historical snapshot and cannot be modified."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_audit_history(self):
        raise UserError(_("Allocation lines are audit history and cannot be deleted."))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_document(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("The document %s no longer exists.", self.document_name or ''))
        return self.move_id._get_records_action()
