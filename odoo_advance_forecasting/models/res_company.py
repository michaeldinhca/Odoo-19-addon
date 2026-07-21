from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    cash_forecast_default_payment_days = fields.Integer(
        string='Default Payment Days',
        default=30,
        help="Used as the expected payment delay for confirmed sale/purchase "
             "orders that have no payment term and no commitment/planned date "
             "to derive a due date from, when computing the cash flow forecast.",
    )
