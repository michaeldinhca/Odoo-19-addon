from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    remittance_capture_enabled = fields.Boolean(
        string="Record Payment Allocations",
        default=True,
        help="When enabled, every payment created with the Register Payment wizard records an "
             "immutable snapshot of the bills and credits it settled. Disable only to pause the "
             "feature; payments created while disabled fall back to the legacy remittance slip.")
    remittance_strict_mode = fields.Boolean(
        string="Strict Allocation Check",
        default=False,
        help="When enabled, a payment registration is refused if the recorded allocation cannot be "
             "reconciled to the payment (unexplained mismatch). When disabled the mismatch is "
             "recorded as a diagnostic on the remittance record and the payment is created normally.")
    remittance_show_note = fields.Boolean(
        string="Show Note on Remittance Slip",
        default=True,
        help="Print the optional payment note on the remittance slip when one is filled in.")
