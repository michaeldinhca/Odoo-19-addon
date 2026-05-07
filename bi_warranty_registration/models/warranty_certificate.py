# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date
import base64
import pytz


class WarrantyCertificate(models.Model):
	_name = "warranty.certificate"
	_description = "Warranty Certificate"
	_rec_name = 'cer_serial_no'
	_inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

	cer_serial_no = fields.Char('Certificate No.')
	warrenty_lot_id = fields.Many2one('stock.lot',string="Lot/Serial No",domain=[('check_warranty','=',True)])
	certificate_product_id = fields.Many2one('product.product',string="Product Name")
	certificate_partner_id = fields.Many2one('res.partner',string="Customer Name")
	certificate_mang_date = fields.Datetime(string="Manufacturing Date")
	warranty_template_id = fields.Many2one("warranty.template",string="Warranty Template")
	certificate_template = fields.Html()
	new_certificate_template = fields.Html()
	stage = fields.Selection([('new', 'New'), ('update', 'Updated')],default="new")
	images_ids = fields.One2many('ir.attachment','product_warrnaty_id','Lab Result Certificate')


	@api.model_create_multi
	def create(self, vals):
		for vals in vals:
			if vals.get('cer_serial_no', _('New')) == _('New'):
				vals['cer_serial_no'] = self.env['ir.sequence'].next_by_code('warranty.certificate')
		return super(WarrantyCertificate, self).create(vals)

	@api.onchange('warranty_template_id')
	def certifictae_template(self):
		for rec in self:
			rec.update({
				"certificate_template": rec.warranty_template_id.warranty_template,
				"new_certificate_template":rec.warranty_template_id.warranty_template
			})
			if rec.certificate_mang_date:
				user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
				date_format = self.env['res.lang']._lang_get(self.env.user.lang).date_format + ' %H:%M:%S'
				final_date = rec.certificate_mang_date.replace(tzinfo=pytz.utc).astimezone(user_tz).strftime(date_format)
			else:
				final_date = "______________"

			if rec.certificate_template:
				if 'certificate_partner_id' in rec.certificate_template:
					partner_name = rec.certificate_template.replace('certificate_partner_id', "______________")
					rec.certificate_template = partner_name
				if 'certificate_product_id' in rec.certificate_template:
					product_name = rec.certificate_template.replace('certificate_product_id', "______________")
					rec.certificate_template = product_name
				if 'warrenty_lot_id' in rec.certificate_template:
					update_lot_id = rec.certificate_template.replace('warrenty_lot_id',"______________")
					rec.certificate_template = update_lot_id
				if 'certificate_mang_date' in rec.certificate_template:
					update_mang_date = rec.certificate_template.replace('certificate_mang_date', "______________")
					rec.certificate_template = update_mang_date

			if rec.new_certificate_template:
				if 'certificate_partner_id' in rec.new_certificate_template:
					partner_name = rec.new_certificate_template.replace('certificate_partner_id', rec.certificate_partner_id.name or "______________")
					rec.new_certificate_template = partner_name
				if 'certificate_product_id' in rec.new_certificate_template:
					product_name = rec.new_certificate_template.replace('certificate_product_id', rec.certificate_product_id.name or "______________")
					rec.new_certificate_template = product_name
				if 'warrenty_lot_id' in rec.new_certificate_template:
					update_lot_id = rec.new_certificate_template.replace('warrenty_lot_id',rec.warrenty_lot_id.name or "______________")
					rec.new_certificate_template = update_lot_id
				if 'certificate_mang_date' in rec.new_certificate_template:
					update_mang_date = rec.new_certificate_template.replace('certificate_mang_date', final_date)
					rec.new_certificate_template = update_mang_date

	@api.onchange('warrenty_lot_id')
	def certifictae_detials(self):
		for rec in self:
			Attachments = self.env['ir.attachment']
			if rec.warrenty_lot_id:
				find_warrenty = self.env['product.warranty'].sudo().search([('product_serial_id','=',rec.warrenty_lot_id.id)],limit=1)
				attachments = self.env['ir.attachment'].sudo().search([('res_model','=','stock.lot'),('res_id','=',find_warrenty.product_serial_id.id)], limit=1)
				rec.update({
					'certificate_product_id':find_warrenty.product_id.id,
					'certificate_partner_id':find_warrenty.partner_id.id,
					'certificate_mang_date':find_warrenty.product_serial_id.create_date,
					'images_ids': [(6, 0, attachments.ids,)]
				})

	def update_template(self):
		for rec in self:
			if rec.warranty_template_id:
				self.certifictae_template()
				rec.update({'certificate_template': rec.new_certificate_template})
				rec.update({'stage': 'update'})
			else:
				raise ValidationError(_("Please Select Template First"))

class WarrantyTemplate(models.Model):
	_name = "warranty.template"
	_description = "Warranty template"
	_rec_name ="template_name"

	template_name = fields.Char(string="Template Name")
	warranty_template = fields.Html()


class ir_attachment(models.Model):
	_inherit='ir.attachment'

	product_warrnaty_id =fields.Many2one('warranty.certificate', 'Warranty Certificate')