# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class productProduct(models.Model):
	_inherit = 'product.product'

	under_warranty = fields.Boolean('Under Warranty',default=False)
	warranty_period = fields.Integer("Warranty Period")
	allow_renewal = fields.Boolean('Allow Renewal',default=False)
	warranty_renewal_time = fields.Integer("Allow Warranty Renewal Times ")
	warranty_renewal_period = fields.Integer("Warranty Renewal Period")
	warranty_renewal_cost = fields.Float("Warranty renewal Cost")
	create_warranty_with_saleorder = fields.Boolean('Create Warranty from Sale Order',default=False)
	create_warranty_with_purchase = fields.Boolean('Create Warranty from Purchase Order',default=False)
	warranty_sale_config = fields.Boolean(compute='_compute_sale_warranty', default=False)
	warranty_purchase_config = fields.Boolean(compute='_compute_purchase_warranty', default=False)
	is_warranty_visible = fields.Boolean(compute='_compute_warranty_visible', default=False)

	def _compute_warranty_visible(self):
		tmp = self.env['warranty.settings'].sudo().search([], order="id desc", limit=1).apply_on
		for line in self:
			if tmp == 'variants':
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
		res = super(productProduct, self).create(vals)
		for val in res:
			template = val.product_tmpl_id
			if template:
				if template.under_warranty:     
					val.under_warranty = template.under_warranty
					val.warranty_period = template.warranty_period
			else:
				template.under_warranty = val.under_warranty
				template.warranty_period = val.warranty_period
			if template.allow_renewal:
				val.allow_renewal = template.allow_renewal
				val.warranty_renewal_time = template.warranty_renewal_time
				val.warranty_renewal_period = template.warranty_renewal_period
				val.warranty_renewal_cost = template.warranty_renewal_cost
			else:
				template.allow_renewal = val.allow_renewal
				template.warranty_renewal_time = val.warranty_renewal_time
				template.warranty_renewal_period = val.warranty_renewal_period
				template.warranty_renewal_cost = val.warranty_renewal_cost
			if template.create_warranty_with_saleorder:
				val.create_warranty_with_saleorder = template.create_warranty_with_saleorder
			else:
				template.create_warranty_with_saleorder = val.create_warranty_with_saleorder
		return res
