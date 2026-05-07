# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .product_product import TRACK_FIELDS_PRODUCT


_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_qbo_sync_done = fields.Boolean(
        string='QuickBooks Synced',
        compute='_compute_qbo_fields',
    )
    is_qbo_taxable = fields.Boolean(
        string='Is QuickBooks Taxable',
        default=True,
        copy=False,
    )
    qbo_mapping_ids = fields.One2many(
        comodel_name='qbo.map.product',
        compute='_compute_qbo_fields',
        string='QuickBooks Mappings',
    )
    is_qbo_update_required = fields.Boolean(
        string='QuickBooks Update Required',
        compute='_compute_is_qbo_update_required',
        inverse='_inverse_is_qbo_update_required',
    )

    @api.depends('product_variant_ids.is_qbo_update_required')
    def _compute_is_qbo_update_required(self):
        for rec in self.with_context(no_mark_quickbooks_update=True):
            rec.is_qbo_update_required = any(rec.product_variant_ids.mapped('is_qbo_update_required'))

    def _inverse_is_qbo_update_required(self):
        for rec in self.with_context(no_mark_quickbooks_update=True):
            rec.product_variant_ids.write({
                'is_qbo_update_required': rec.is_qbo_update_required,
            })

    @api.depends('product_variant_ids')
    def _compute_qbo_fields(self):
        company = self.env.company

        for rec in self:
            is_qbo_sync_done = product_ids = False

            if len(rec.product_variant_ids) == 1:
                product = rec.product_variant_id.with_company(company)

                product_ids = product.qbo_mapping_ids
                is_qbo_sync_done = product.is_qbo_sync_done

            rec.write({
                'qbo_mapping_ids': product_ids,
                'is_qbo_sync_done': is_qbo_sync_done,
            })

    def write(self, vals):
        result = super(ProductTemplate, self).write(vals)

        if self.env.context.get('no_mark_quickbooks_update'):
            return result

        if set(TRACK_FIELDS_PRODUCT).intersection(set(vals.keys())):
            for rec in self.filtered('product_variant_ids.qbo_mapping_ids'):
                rec.product_variant_ids.filtered('qbo_mapping_ids').mark_for_qbo_update()

        return result

    def action_export_to_quickbooks(self):
        return self.mapped('product_variant_ids').action_export_to_quickbooks()

    def to_qbo_json(self):
        self.ensure_one()

        if len(self.product_variant_ids) != 1:
            raise UserError(_('Only one product variant is supported for template.'))

        return self.product_variant_ids.to_qbo_json()
