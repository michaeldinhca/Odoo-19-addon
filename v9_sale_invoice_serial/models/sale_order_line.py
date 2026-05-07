# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError


class sale_order_line(models.Model):
	_inherit = "sale.order.line"

	serial_no = fields.Many2one('stock.lot',string='Serial Number',domain="[('product_id', '=', product_id)]")

	_sql_constraints = [
		('serial_no_uniq', 'unique (order_id,serial_no)', 'You can not take same Serial Number/Lot in Sale Order Line!!')
	]

	def _prepare_invoice_line(self, **optional_values):
		res = super(sale_order_line, self)._prepare_invoice_line(**optional_values)
		res.update({'serial_no':self.serial_no.id})
		return res

	@api.onchange('serial_no')
	def onchange_serial_number(self):
		serial_no_list = []
		for line in self :
			if line.serial_no:
				serial_no_list.append(line.serial_no.id)
				Product = self.env['stock.lot']
				products_ids = Product.search([('name', '=', line.serial_no.name)])
				if not products_ids:
					raise UserError(_(' %s Serial number is not available in system!!') % line.serial_no.name)
				for product in products_ids:
					if not product.product_qty > 0.0 :
						raise UserError(_('Stock not available with %s serial/lot number.') % line.serial_no.name)


class sale_order(models.Model):
	_inherit = "sale.order"


	def action_confirm(self):
		res = super(sale_order, self).action_confirm()
		for order in self:
			serial_no_list = []
			for line in order.order_line:
				if line.serial_no:
					serial_no_list.append(line.serial_no.id)
					Product = self.env['stock.lot']
					products_ids = Product.search([('name', '=', line.serial_no.name)])
					for product in products_ids:
						if not product.product_qty > 0.0 :
							raise UserError(_('Stock not available with %s serial/lot number.') % line.serial_no.name)

		return res






