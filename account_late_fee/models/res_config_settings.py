from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    late_fee_enabled = fields.Boolean(
        related='company_id.late_fee_enabled', readonly=False)
    late_fee_notification_email = fields.Char(
        related='company_id.late_fee_notification_email', readonly=False)
