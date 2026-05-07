# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import models, fields, _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class QuickbooksIntegrationDefaultsMixin(models.AbstractModel):
    _name = 'quickbooks.integration.defaults.mixin'
    _description = 'Quickbooks Integration Defaults Mixin'

    # Required for the relation `company_id.account_stock_valuation_id`
    company_id = fields.Many2one(comodel_name='res.company')

    qi_default_stock_valuation_account_id = fields.Many2one(
        related='company_id.account_stock_valuation_id',
        string='Default Stock Valuation Account',
        readonly=False,
        help=(
            'This account is used in case no Stock Valuation Account is set '
            'neither on Product Category nor on Company.'
        ),
    )

    qi_default_write_off_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Default Write-off Account',
        help=(
            'Write-off account is used to record difference between payment downloaded from QuickBooks '
            'and Invoice total in Odoo in case QuickBooks Invoice is marked as Paid and we also need to '
            'closed it on Odoo side.'
        ),
    )

    qi_adjust_inventory_account_id = fields.Many2one(
        comodel_name='qbo.map.account',
        string='Adjust Inventory Account (Quickbooks)',
        help=(
            'Account that will be used to adjust inventory in Quickbooks. '
            'Usually it named as "Inventory Shrinkage" or something like that.'
        ),
    )

    qi_default_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Default Payment Journal',
    )

    def get_qbo_default_stock_valuation_account(self):
        self.ensure_one()
        return self.qi_default_stock_valuation_account_id

    def get_qbo_adjust_inventory_account_code(self):
        self.ensure_one()

        account = self.qi_adjust_inventory_account_id
        if not account:
            raise ValidationError(
                _('Adjust Inventory Account is not set for the %s integration.') % self.display_name
            )

        return account.qbo_id

    def get_qbo_default_income_account(self):
        self.ensure_one()
        return self.env['account.account']

    def get_qbo_default_expense_account(self):
        self.ensure_one()
        return self.env['account.account']
