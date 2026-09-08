from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    late_fee_exempt = fields.Boolean(
        string='Exempt from Late Fees',
        help='If checked, invoices for this customer will never be '
             'charged a late fee, regardless of Late Fee Model '
             'configuration.')
