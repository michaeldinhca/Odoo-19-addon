# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ProductTemplate(models.Model):

	_inherit ="product.template"

	is_extended_warranty = fields.Boolean('Extended Warranty',default=False)

	extended_warranty_ids =  fields.One2many('product.extended.warranty','product_id',string="Extended Warranty")


	@api.model
	def _load_pos_data_fields(self, config_id):
		params = super()._load_pos_data_fields(config_id)

		params += ['is_extended_warranty', 'extended_warranty_ids']
		return params

	def _server_date_to_domain(self, domain):
		data_dom = super()._server_date_to_domain(domain)
		return data_dom

	@api.model
	def _load_pos_data_read(self, records, config):
		read_records = super()._load_pos_data_read(records.sudo(), config)
		
		return read_records or []
		

class ProductExtendedWarranty(models.Model):

	_name ="product.extended.warranty"
	_inherit = 'pos.load.mixin'
	_description = "Product Extended Warranty"

	extended_warranty_period = fields.Integer("Extended Warranty Period")
	extended_warranty_percentage = fields.Float("Extended Warranty Percentage (%)")
	extended_warranty_amount =  fields.Float("Extended Warranty Amount")
	product_id = fields.Many2one('product.template')



	@api.model
	def _load_pos_data_fields(self, config_id):
		return ['extended_warranty_period','extended_warranty_percentage','extended_warranty_amount','product_id']


	def _load_pos_data(self, data):
		domain = []
		fields = self._load_pos_data_fields(data)
		data = self.search_read(domain, fields, load=False, )
		return {
			'data': data,
			'fields': fields
		}

	def _server_date_to_domain(self, domain):
		data_dom = super()._server_date_to_domain(domain)
		return data_dom

	@api.model
	def _load_pos_data_read(self, records, config):
		read_records = super()._load_pos_data_read(records.sudo(), config)
		
		return read_records or []

	@api.onchange('extended_warranty_percentage')
	def _onchange_extended_warranty_percentage(self):
		if self.extended_warranty_percentage:
			amount = (self.extended_warranty_percentage * self.product_id.list_price) / 100 + self.product_id.list_price

			self.update({'extended_warranty_amount': amount})



class ProductProduct(models.Model):

	_inherit ="product.product"

	is_extended_warranty = fields.Boolean('Extended Warranty',default=False)
	extended_warranty_ids = fields.One2many(related='product_tmpl_id.extended_warranty_ids')

	@api.model
	def _load_pos_data_fields(self, config_id):
		params = super()._load_pos_data_fields(config_id)

		params += ['is_extended_warranty', 'extended_warranty_ids','warranty_period']
		return params

	def _server_date_to_domain(self, domain):
		data_dom = super()._server_date_to_domain(domain)
		return data_dom

	@api.model
	def _load_pos_data_read(self, records, config):
		read_records = super()._load_pos_data_read(records.sudo(), config)
		
		return read_records or []


class AccountMoveLine(models.Model):

	_inherit = "account.move.line"

	warranty_period_extended = fields.Integer()

class POSSession(models.Model):
	_inherit = 'pos.session'

	@api.model
	def _load_pos_data_models(self, config_id):
		data = super()._load_pos_data_models(config_id)
		data += ['product.extended.warranty']
		return data

	