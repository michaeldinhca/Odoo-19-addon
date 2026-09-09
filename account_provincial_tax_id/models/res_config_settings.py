from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    provincial_tax_id_source = fields.Selection(
        related='company_id.provincial_tax_id_source', readonly=False)
