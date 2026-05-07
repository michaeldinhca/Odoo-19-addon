# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError


class QuickbooksIntegration(models.Model):
    _name = 'quickbooks.integration'
    _description = 'Quickbooks Integration'

    _inherit = [
        'quickbooks.integration.auth.mixin',
        'quickbooks.integration.defaults.mixin',
        'quickbooks.integration.import.mixin',
        'quickbooks.integration.automation.mixin',
    ]

    _sql_constraints = [
        (
            'company_id_uniq', 'unique(company_id)',
            'Company must have only one Quickbooks Integration!'
        ),
    ]

    name = fields.Char(
        string='Name',
        required=True,
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('active', 'Active'),
        ],
        string='State',
        default='draft',
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
    )

    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
    )

    @property
    def is_active(self):
        return self.state == 'active'

    @property
    def qbo_send_stock_property(self):
        return self.is_active and self.allow_update_products and self.sync_product_stock

    def action_active(self):
        for rec in self:
            if not rec.qb_access_granted:
                raise ValidationError(_(
                    '%s: Please connect to QuickBooks first (grant app access) before activating.'
                ) % rec.display_name)

            rec.state = 'active'

    def action_draft(self):
        self.write({
            'state': 'draft',
        })

    @api.model
    def get_quickbooks_integrations(self, domain: list = None):
        records = self.sudo().search([('state', '=', 'active')])
        if domain:
            records = records.filtered_domain(domain)
        return records

    def currency_name_belong_odoo_company(self, currency_name: str):
        self.ensure_one()
        return self.currency_id.name == currency_name

    def write(self, vals):
        result = super().write(vals)

        # Skip rest of the logic if skip_write_actions is set
        if self.env.context.get('skip_write_actions'):
            return result

        add_values = dict()

        # 1. Check enable_invoices_auto_export field
        if 'enable_invoices_auto_export' in vals and not vals['enable_invoices_auto_export']:
            add_values.update(
                enable_payments_sync_in=False,
                enable_payments_sync_out=False,
            )

        # 2. Check enable_updates_auto_export field
        if 'enable_updates_auto_export' in vals and not vals['enable_updates_auto_export']:
            add_values.update(
                allow_update_partners=False,
                allow_update_products=False,
            )

        # 3. Check include_product_to_invoice field
        if 'include_product_to_invoice' in vals and not vals['include_product_to_invoice']:
            add_values.update(
                sync_product_as_category=False,
                send_storable_product_as_consumable=False,
            )

        # 4. Check sync_product_as_category field
        if vals.get('sync_product_as_category'):
            add_values['send_storable_product_as_consumable'] = False

        # 5. check send_storable_product_as_consumable field
        if vals.get('send_storable_product_as_consumable'):
            add_values['sync_product_as_category'] = False

        # 6. Check qb_is_us_company field
        if vals.get('qb_is_us_company'):
            add_values['export_invoice_as_tax_included'] = False

        if add_values:
            self.with_context(skip_write_actions=True) \
                .write(add_values)

        return result

    def action_get_all_pending_invoices(self):
        records = self.env['account.move']

        for qi in self.get_quickbooks_integrations():
            records |= qi._search_to_qbo_invoices()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Pending Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', records.ids)],
            'search_view_id': self.env.ref('account.view_account_invoice_filter').id,
        }

    def action_get_all_pending_payments(self):
        records = self.env['account.payment']

        for qi in self.get_quickbooks_integrations():
            records |= qi._search_to_qbo_payments()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Pending Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', records.ids)],
        }

    def action_get_all_pending_partners(self):
        records = self.env['res.partner'].search([
            ('is_qbo_update_required', '=', True),
        ])

        return {
            'type': 'ir.actions.act_window',
            'name': _('Pending Partners'),
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('id', 'in', records.ids)],
        }

    def action_get_all_pending_products(self):
        records = self.env['product.product'].search([
            ('is_qbo_update_required', '=', True),
        ])

        return {
            'type': 'ir.actions.act_window',
            'name': _('Pending Products'),
            'res_model': 'product.product',
            'view_mode': 'list,form',
            'domain': [('id', 'in', records.ids)],
        }
