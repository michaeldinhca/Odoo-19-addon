# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class WarrantyInvoice(models.Model):
	_inherit = 'account.move'

	warranty_invoice = fields.Boolean('Warranty Renew Invoice')
	warranty_reg_id = fields.Many2one('product.warranty', 'Warranty')

	def action_post(self):
		res = super(WarrantyInvoice, self).action_post()
		if self.warranty_reg_id:
			self.warranty_reg_id.update({'state': 'in_progress'})
		for value in self:
			if value.origin_payment_id:
				for val in value.origin_payment_id:
					if val.state != "posted":
						val.action_post()
			else:
				if value.state != "posted":
					value._post(soft=False)
		return res
