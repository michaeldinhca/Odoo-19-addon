# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, fields, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    quickbooks_integration_ids = fields.One2many(
        comodel_name='quickbooks.integration',
        inverse_name='company_id',
        string='Quickbooks Connections',
    )

    @property
    def quickbooks_integration(self):
        return self.quickbooks_integration_ids.filtered(lambda x: x.is_active)

    def raise_if_no_qbo_auth(self):
        qi = self.quickbooks_integration

        if not qi:
            raise ValidationError(_('%s: QuickBooks integration is not set!') % self.name)

        if not qi.qb_access_granted:
            raise ValidationError(_('%s: QuickBooks access is not granted!') % self.name)
