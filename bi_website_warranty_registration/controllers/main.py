# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo.http import request
from odoo import http, _
from datetime import datetime, date
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from dateutil.relativedelta import relativedelta


class WarrantyRegistration(http.Controller):

	@http.route(['/warranty-registration'], type='http', auth="public", website=True, sitemap=False)
	def warranty(self, page=1, **kwargs):
		countries = request.env['res.country'].sudo().search([])
		states = request.env['res.country.state'].sudo().search([])
		values ={}
		values.update({
					'countries': countries,
					'states': states,
			})

		return request.render("bi_website_warranty_registration.bi_warranty_reg",values)

	@http.route(['/warranty-thankyou'], type='http', auth="public", website=True, sitemap=False)
	def registration_submit(self, **post):
		if 'is_warranty' not in post:
			return request.redirect("/my")

		warranty_obj = request.env['product.warranty']
		serial_no_obj = request.env['stock.lot']
		
		name = post['name']
		phone = post['phone']
		email = post['email']
		company_name = post['company_name']
		zip1 = post['zip']
		city =  post['city']
		street = post['street']
		if post['state_id'] != "": 
			state_id = int(post['state_id'])
		else:
			state_id = False
			
		if post['country_id'] != "":
			country_id = int(post['country_id'])
		else:
			country_id = False
			
		comment = post['comment']
		serial_no = post['product_serial_id']
		merchant = post['merchant']
		product_id = int(post['product_id'])
		w_type = post['type']
		serial_no_type = post['serial_no_type']


		warranty_type = []
		if w_type == 'free':
			warranty_type = 'free'
		if w_type == 'paid':
			warranty_type = 'paid'
		
		customer_obj = request.env['res.partner'].sudo().search([('name','=', name)])
		
		if not customer_obj:
			customer_obj.sudo().create({
				'name': name,
				'street': street,
				'city': city,
				'zip': zip1,
				'state_id': state_id,
				'country_id': int(country_id),
				'company_name': company_name,
				'email': email,
				'phone': phone,
			})
		
		customer = []
		customer_warranty_obj = request.env['res.partner'].sudo().search([('name','=', name)])
		for cust in customer_warranty_obj:
			customer = cust.id
			
		
		serial_lot_w = request.env['stock.lot'].sudo().search([('product_id','=', int(product_id)),('name','=', serial_no)])
		warranty_serial_exist = request.env['product.warranty'].sudo().search([('product_serial_id','=', serial_no)])
		serial_no_valid = []
		
		for serial_exist in warranty_serial_exist:
			
			return request.redirect("/warranty-registration?warranty_exist=%s" % _("Warranty Already Created For This Serial No !"))
				
		if serial_no_type == 'exist':
			if serial_lot_w:
				serial_no_valid = serial_lot_w.id
			else:
				return request.redirect("/warranty-registration?warranty_msg=%s" % _("Invalid Serial No !"))
		
		elif serial_no_type == 'new':
			if serial_lot_w:
				return request.redirect("/warranty-registration?lot_already_exist=%s" % _("This Serial No already created! Please add different serial no. if want to create with new new serial no."))
			else:
				serial_no_obj.sudo().create({'name':serial_no,'product_id':int(product_id),'company_id':request.env.user.company_id.id})
				new_serial_no = request.env['stock.lot'].sudo().search([('product_id','=', int(product_id)),('name','=', serial_no)])
				serial_no_valid = new_serial_no.id
			
		inv_obj = request.env['account.move']
		prod_obj = request.env['product.product'].sudo().search([('id','=', product_id)])
		
		account_id = False
		name = _('Warranty')
		for pr in prod_obj:
			if pr:
				if not pr.property_account_income_id:
					account_id = pr.categ_id.property_account_income_categ_id.id
					#return request.redirect("/warranty-registration?warranty_renew_acc=%s" % _("Configure Income and Expense account in Product"))
				else:
					account_id = pr.property_account_income_id.id
				price_u = pr.warranty_renewal_cost
		
			
		if w_type == 'paid':

			warr = warranty_obj.sudo().create({
						
						'partner_id': customer,
						'phone': phone,        			
						'email': email,
						'comment': comment,
						'product_serial_id': serial_no_valid,
						'product_id': product_id,
						'merchant': merchant,
						'warranty_type': warranty_type,
						'warranty_cost': price_u,
						'state': 'invoiced',
						'warranty_sales_person': request.uid,
		
				})

			warr.sudo().state_update()
			warr.sudo().create_invoice()
		
		if w_type == 'free':
			
			warranty_obj.sudo().create({
						
						'partner_id': customer,
						'phone': phone,        			
						'email': email,
						'comment': comment,
						'product_serial_id': serial_no_valid,
						'product_id': product_id,
						'merchant': merchant,
						'warranty_type': warranty_type,
						'warranty_sales_person': request.uid,
		
				})
							   
		return request.render("bi_website_warranty_registration.reg_thankyou")
