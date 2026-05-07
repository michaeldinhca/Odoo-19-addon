# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from functools import partial
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

class POSConfig(models.Model):

    _inherit ="pos.config"

    create_warranty = fields.Boolean('Create Warranty from POS')	



class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def _default_pos_config(self):
        # Default to the last modified pos.config.
        active_model = self.env.context.get('active_model', '')
        if active_model == 'pos.config':
            return self.env.context.get('active_id')
        return self.env['pos.config'].search([('company_id', '=', self.env.company.id)], order='write_date desc', limit=1)
        
    pos_config_id = fields.Many2one('pos.config', string="Point of Sale", default=lambda self: self._default_pos_config())

    create_warranty = fields.Boolean(related='pos_config_id.create_warranty', readonly=False)

class Warranty(models.Model):
    _inherit = 'product.warranty'

    pos_id = fields.Many2one('pos.order',"POS Order")
    extended_warranty_history_ids = fields.One2many('extended.warranty.history', 'warranty_id', 'Warranty History', readonly=True)
    extended_warranty_claim_ids = fields.One2many('extended.warranty.claim', 'warranty', 'Claims', readonly=True)
    is_extended_warranty = fields.Boolean('Extended Warranty',default=False)
    
class ExtendedWarrantyHistory(models.Model):
    _name = "extended.warranty.history"

    ex_warranty_start_date = fields.Date("Extended Warranty Start Date")
    ex_warranty_end_date = fields.Date("Extended Warranty End Date")
    is_extended_warranty = fields.Boolean('Extended Warranty',default=False)
    extended_warranty_period = fields.Integer("Extended Warranty Period")
    extended_warranty_percentage = fields.Float("Extended Warranty Percentage (%)")
    extended_warranty_amount =  fields.Float("Extended Warranty Amount")
    warranty_id = fields.Many2one('product.warranty', 'Warranty')



class PosOrderInherit(models.Model):

    _inherit ="pos.order"

    def check_warranty_reg(self):

        used_lots = [] 
        all_lots = []
        warranty = self.env['product.warranty'].sudo().search([])
        all_lts = self.env['stock.lot'].search([])
        for wrnty in warranty :
            if wrnty and wrnty.product_serial_id :
                used_lots.append(wrnty.product_serial_id.name)
    
        for lts in all_lts :
            all_lots.append(lts.name)
        return [used_lots,all_lots]

    @api.depends('lines')
    def _compute_warranty_pos(self):
        for res in self:
            count = 0
            warranty = self.env['product.warranty'].search_count([('pos_id','=',res.id)])
            res.pos_warranty = warranty

    pos_warranty = fields.Integer(string="warranty",compute="_compute_warranty_pos")

    @api.model
    def _get_invoice_lines_values(self, line_values, pos_order_line):
        return {
            'product_id': line_values['product_id'].id,
            'quantity': line_values['quantity'],
            'discount': line_values['discount'],
            'price_unit': line_values['price_unit'],
            'name': line_values['name'],
            'tax_ids': [(6, 0, line_values['tax_ids'].ids)],
            'product_uom_id': line_values['uom_id'].id,
            'warranty_period_extended': int(pos_order_line.extended_warranty_line.split(' ')[0]) if pos_order_line.extended_warranty_line else 0,
        }
    # def _prepare_invoice_lines(self, order_line):
    #     #apply customer language on invoice
    #     print("55555",order_line)
    #     name = order_line.product_id.with_context(lang=order_line.order_id.partner_id.lang or self.env.user.lang).get_product_multiline_description_sale()
    #     return {
    #         'product_id': order_line.product_id.id,
    #         'quantity': order_line.qty if self.amount_total >= 0 else -order_line.qty,
    #         'discount': order_line.discount,
    #         'price_unit': order_line.price_unit,
    #         'name': name,
    #         'tax_ids': [(6, 0, order_line.tax_ids_after_fiscal_position.ids)],
    #         'product_uom_id': order_line.product_uom_id.id,
    #         'warranty_period_extended':int(order_line.extended_warranty_line.split(' ')[0]) if order_line.extended_warranty_line else 0,
    #     }


    
    @api.model
    def _process_order(self, order, existing_order):
        res = super(PosOrderInherit, self)._process_order(order,existing_order)
        orders = self.env['pos.order'].browse(res)
        for odr in orders :
            if odr.config_id.create_warranty :
                for line in odr.lines :
                    if  line.product_id.under_warranty == True:
                        for pack_lot in line.pack_lot_ids :
                            lot = self.env['stock.lot'].search([('name','=',pack_lot.lot_name), ('product_id', '=', line.product_id.id)])
                            if lot :
                                val = {
                                    'partner_id' : odr.partner_id.id if odr.partner_id.id else odr.user_id.partner_id.id,
                                    'product_id' : line.product_id.id,
                                    'is_extended_warranty':True if line.extended_warranty_line else  False,
                                    'phone' : odr.partner_id.phone,
                                    'email' : odr.partner_id.email,
                                    'product_serial_id' : lot.id,
                                    'pos_id' : odr.id,
                                }
                                warranty = self.env['product.warranty'].create(val)

                                extend_amount = 0

                                extend_percentage = 0

                                extend_history_obj = self.env['extended.warranty.history']
                                if line.extended_warranty_line:
                                    year_w = int(line.extended_warranty_line.split(' ')[0])
                                    date_1 = (warranty.warranty_create_date) + relativedelta(years=+ year_w)
                                    extend_warr_period = int(line.extended_warranty_line.split(' ')[0])
                                    for ex_warr in line.product_id.extended_warranty_ids:
                                        if ex_warr.extended_warranty_period == extend_warr_period:
                                            extend_percentage = ex_warr.extended_warranty_percentage



                                    extend_amount = (extend_percentage * line.product_id.list_price) / 100 + line.product_id.list_price
                                
                                    extend_history_obj.create({
                                        'ex_warranty_start_date': datetime.now(),
                                        'ex_warranty_end_date': date_1,
                                        'extended_warranty_period': int(line.extended_warranty_line.split(' ')[0]),
                                        'extended_warranty_percentage': extend_percentage,
                                        'extended_warranty_amount':extend_amount,
                                        'warranty_id': warranty.id,
                                        'is_extended_warranty':True if line.extended_warranty_line else  False,
                                    })
        return res

    def button_warranty(self):
        return{
            'name': _('warranty'),
            'view_mode': 'list,form',
            'res_model': 'product.warranty',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('pos_id', '=',self.id )],
        }


class PosOrderLineInherit(models.Model):

    _inherit ="pos.order.line"

    extended_warranty_line = fields.Char()
    warranty_period = fields.Integer()

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)

        params += ['extended_warranty_line', 'warranty_period']
        return params


    def _order_line_fields(self, line, session_id=None):
        result = super()._order_line_fields(line, session_id)
        vals = result[2]
        if vals.get('extended_warranty_line', False):
            vals['extended_warranty_line'] = vals['extended_warranty_line']
        return result