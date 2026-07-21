from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cash_forecast_default_payment_days = fields.Integer(
        related='company_id.cash_forecast_default_payment_days',
        readonly=False,
        string='Default Payment Days',
    )
