# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models, _


class QuickbooksPartnerTypeWizard(models.TransientModel):
    _name = 'quickbooks.partner.type.wizard'
    _description = 'Explicit indication of partner type.'

    qbo_partner_type = fields.Selection(
        selection=[
            ('customer', 'Customer'),
            ('vendor', 'Vendor'),
            ('customer,vendor', 'Both of them'),
        ],
        string='Export Partner(s) as',
        default='customer',
    )

    def export_to_quickbooks(self):
        active_ids = self.env.context.get('active_partner_ids')
        partners = self.env['res.partner'].browse(active_ids)

        partners \
            .with_context(with_qbo_partner_type=self.qbo_partner_type) \
            .action_export_to_quickbooks()

        return {
            'type': 'ir.actions.act_window_close',
        }

    def open_form(self):
        return {
            'name': _('QuickBooks Partner Export Options'),
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
