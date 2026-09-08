from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    late_fee_enabled = fields.Boolean(
        string='Late Fees Enabled', default=True,
        help='Company-wide switch. When off, no late fees are generated '
             'for this company, regardless of Late Fee Model '
             'configuration.')
    late_fee_notification_email = fields.Char(
        string='Late Fee Notification Email',
        help='CC address added to every late fee notification email sent '
             'to customers.')
