# See LICENSE file for full copyright and licensing details.

from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def validate_config_for_quickbooks(self):
        self.ensure_one()
        wizard = self.env['quickbooks.installation.wizard'].create({})
        return wizard.check_odoo_setup_for_quickbooks()
