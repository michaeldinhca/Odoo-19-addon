# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _
from odoo.tools.float_utils import float_compare, float_round, float_is_zero



class StockRule(models.Model):
	_inherit = 'stock.rule'

	def _get_stock_move_values(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values):
		result = super(StockRule, self)._get_stock_move_values(product_id, product_qty, product_uom, location_id, name, origin, company_id, values)
		sale_line_id = values.get('sale_line_id')
		serial_number = False
		if sale_line_id:
			serial_number = self.env['sale.order.line'].browse(sale_line_id).serial_no.id
		result.update({
			'serial_no':serial_number or False,
		})
		return result

