# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    under_warranty = fields.Boolean('Under Warranty',default=False)
    warranty_period = fields.Integer("Warranty Period")
    allow_renewal = fields.Boolean('Allow Renewal',default=False)
    warranty_renewal_time = fields.Integer("Allow Warranty Renewal Times ")
    warranty_renewal_period = fields.Integer("Warranty Renewal Period")
    warranty_renewal_cost = fields.Float("Warranty renewal Cost")
    create_warranty_with_saleorder = fields.Boolean('Create Warranty from Sale Order',default=False)
    create_warranty_with_purchase = fields.Boolean('Create Warranty from Purchase Order',default=False)
    warranty_sale_config = fields.Boolean(compute='_compute_sale_warranty',default=False)
    warranty_purchase_config = fields.Boolean(compute='_compute_purchase_warranty', default=False)
    is_warranty_visible = fields.Boolean(compute='_compute_warranty_visible',default=False)

    def _compute_warranty_visible(self):
        tmp = self.env['warranty.settings'].sudo().search([], order="id desc", limit=1).apply_on
        for line in self:
            if tmp == 'category':
                line.is_warranty_visible = True

            else:
                line.is_warranty_visible = False

    def _compute_sale_warranty(self):
        tmp = self.env['warranty.settings'].sudo().search([], order="id desc", limit=1).warranty_from
        for line in self:
            if tmp == 'sale':
                line.warranty_sale_config = True
            else:
                line.warranty_sale_config = False

    def _compute_purchase_warranty(self):
        tmp = self.env['warranty.settings'].sudo().search([], order="id desc", limit=1).warranty_from
        for line in self:
            if tmp == 'purchase':
                line.warranty_purchase_config = True
            else:
                line.warranty_purchase_config = False

    @api.model_create_multi
    def create(self, vals):
        res = super(ProductCategory, self).create(vals)
        product_ids = self.env['product.template'].search([('categ_id', 'child_of', self.ids)])
        for rec in self:
            if product_ids:
                for template in product_ids:
                    if rec.under_warranty:
                        template.under_warranty = rec.under_warranty
                        template.warranty_period = rec.warranty_period
                        template.allow_renewal = rec.allow_renewal
                        template.warranty_renewal_time = rec.warranty_renewal_time
                        template.warranty_renewal_period = rec.warranty_renewal_period
                        template.warranty_renewal_cost = rec.warranty_renewal_cost
                        template.create_warranty_with_saleorder = rec.create_warranty_with_saleorder
                        template.create_warranty_with_purchase = rec.create_warranty_with_purchase

        return res


    def write(self, vals):
        res = super(ProductCategory, self).write(vals)
        product_ids = self.env['product.template'].search([('categ_id', 'child_of', self.ids)])
        for rec in self:
            if product_ids:
                for template in product_ids:
                    if rec.under_warranty:
                        template.under_warranty = rec.under_warranty
                        template.warranty_period = rec.warranty_period
                        template.allow_renewal = rec.allow_renewal
                        template.warranty_renewal_time = rec.warranty_renewal_time
                        template.warranty_renewal_period = rec.warranty_renewal_period
                        template.warranty_renewal_cost = rec.warranty_renewal_cost
                        template.create_warranty_with_saleorder = rec.create_warranty_with_saleorder
                        template.create_warranty_with_purchase = rec.create_warranty_with_purchase

        return res