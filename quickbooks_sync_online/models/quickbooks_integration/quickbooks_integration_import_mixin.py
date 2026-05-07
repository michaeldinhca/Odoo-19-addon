# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, _


class QuickbooksIntegrationImportMixin(models.AbstractModel):
    _name = 'quickbooks.integration.import.mixin'
    _description = 'Quickbooks Integration Import Mixin'

    def import_all_from_qbo(self):
        self.ensure_one()

        self.import_partners_from_qbo()
        self.import_products_from_qbo()
        self.import_accounts_from_qbo()
        self.import_taxes_from_qbo()
        self.import_terms_from_qbo()
        self.import_payment_methods_from_qbo()
        self.import_departments_from_qbo()

        return self.action_display_notification_and_open_form(_('All Types'))

    def import_partners_from_qbo(self):
        self.ensure_one()
        self.env['qbo.map.partner'].fetch_resource_data_from_qbo(self.id)
        return self.action_display_notification_and_open_form(_('Partners'))

    def import_products_from_qbo(self):
        self.ensure_one()
        self.env['qbo.map.product'].fetch_resource_data_from_qbo(self.id, job_alias_in='Products')
        return self.action_display_notification_and_open_form(_('Products'))

    def import_accounts_from_qbo(self):
        self.ensure_one()
        self.env['qbo.map.account'].fetch_resource_data_from_qbo(self.id)
        return self.action_display_notification_and_open_form(_('Accounts'))

    def import_taxes_from_qbo(self):
        self.ensure_one()
        self.env['qbo.map.tax'].fetch_resource_data_from_qbo(self.id)
        return self.action_display_notification_and_open_form(_('Taxes'))

    def import_terms_from_qbo(self):
        self.ensure_one()
        self.env['qbo.map.term'].fetch_resource_data_from_qbo(self.id, job_alias_in='Payment Terms')
        return self.action_display_notification_and_open_form(_('Payment Terms'))

    def import_payment_methods_from_qbo(self):
        self.ensure_one()
        self.env['qbo.map.payment.method'].fetch_resource_data_from_qbo(self.id, job_alias_in='Payment Methods')
        return self.action_display_notification_and_open_form(_('Payment Methods'))

    def import_departments_from_qbo(self):
        self.ensure_one()
        self.env['qbo.map.department'].fetch_resource_data_from_qbo(self.id)
        return self.action_display_notification_and_open_form(_('Departments'))

    def action_display_notification_and_open_form(self, name: str):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('%s: Import Job was created') % name,
                'type': 'success',
                'sticky': False,
                'next': self.action_open_import_form(),
            }
        }

    def action_open_import_form(self):
        self.ensure_one()
        view = self.env.ref('quickbooks_sync_online.quickbooks_integration_import_form')

        return {
            'type': 'ir.actions.act_window',
            'name': _('Initial Import: %s') % self.display_name,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
        }

    def action_close(self):
        return {
            'type': 'ir.actions.act_window_close',
        }
