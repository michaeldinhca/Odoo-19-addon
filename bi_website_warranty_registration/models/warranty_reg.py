# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from datetime import datetime, date
from dateutil.relativedelta import relativedelta


class Website(models.Model):
    _inherit = 'website'

    def get_country_list(self):            
        country_ids=self.env['res.country'].search([])
        return country_ids
        
    def get_state_list(self):            
        state_ids=self.env['res.country.state'].search([])
        return state_ids
        
    def get_product_list(self):            
        product_ids=self.env['product.product'].search([('sale_ok','=','True'), ("website_published", "=", True),("under_warranty", "=", True)])
        return product_ids
        
    def get_serial_list(self):            
        serial_ids=self.env['stock.lot'].search([])
        return serial_ids
    
    def get_customer_list(self):            
        partners_ids=self.env['res.partner'].search([])
        return partners_ids

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

