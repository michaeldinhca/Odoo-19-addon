from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    remittance_capture_enabled = fields.Boolean(
        related='company_id.remittance_capture_enabled', readonly=False)
    remittance_strict_mode = fields.Boolean(
        related='company_id.remittance_strict_mode', readonly=False)
    remittance_show_note = fields.Boolean(
        related='company_id.remittance_show_note', readonly=False)
