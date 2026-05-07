# See LICENSE file for full copyright and licensing details.

from odoo import models, _
from odoo.addons.base.models.ir_module import assert_log_admin_access


QUICKBOOKS_SYNC_ONLINE_MODULE = 'quickbooks_sync_online'


class IrModule(models.Model):
    _inherit = 'ir.module.module'

    @assert_log_admin_access
    def button_immediate_install(self):
        result = super(IrModule, self).button_immediate_install()

        if len(self) == 1 and self.name in QUICKBOOKS_SYNC_ONLINE_MODULE:
            return self.open_quickbooks_installation_wizard()

        return result

    @assert_log_admin_access
    def button_immediate_upgrade(self):
        result = super(IrModule, self).button_immediate_upgrade()

        if len(self) == 1 and self.name == QUICKBOOKS_SYNC_ONLINE_MODULE:
            return self.open_quickbooks_installation_wizard()

        return result

    def open_quickbooks_installation_wizard(self):
        wizard = self.env['quickbooks.installation.wizard'].create({})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Let\'s ensure a seamless setup!'),
            'res_model': 'quickbooks.installation.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
