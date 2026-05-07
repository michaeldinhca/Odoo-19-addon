# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    serial_no =  fields.Many2one('stock.lot',string='Serial Number',domain="[('product_id', '=', product_id)]")

    _sql_constraints = [
        ('serial_no_uniq', 'unique (order_id,serial_no)', 'You can not take same Serial Number/Lot in Sale Order Line!!')
    ]

    def _prepare_invoice_line(self, **optional_values):
        res = super(PurchaseOrderLine, self)._prepare_invoice_line(**optional_values)
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



class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    warranty_sale = fields.Integer(string="warranty", compute="_compute_warranty_sale")


    @api.depends('order_line')
    def _compute_warranty_sale(self):
        for res in self:
            warranty = self.env['product.warranty'].sudo().search_count([('po_id', '=', res.id)])
            res.update({'warranty_sale': warranty})

    def button_confirm(self):
        res = super(PurchaseOrder, self).button_confirm()
        for order in self:
            serial_no_list = []
            for line in order.order_line:
                if line.serial_no:
                    serial_no_list.append(line.serial_no.id)
                    Product = self.env['stock.lot']
                    products_ids = Product.search([('name', '=', line.serial_no.name)])
                    for product in products_ids:
                        if not product.product_qty > 0.0:
                            raise UserError(_('Stock not available with %s serial/lot number.') % line.serial_no.name)


        for line in self.order_line:
            if 'serial_no' in self.env['purchase.order.line']._fields:
                if line.serial_no and line.product_id.create_warranty_with_purchase == True and line.product_id.under_warranty == True:
                    self.env['product.warranty'].create({
                        'partner_id': self.partner_id.id,
                        'product_id': line.product_id.id,
                        'phone': self.partner_id.phone,
                        'email': self.partner_id.email,
                        'product_serial_id': line.serial_no.id,
                        'po_id': self.id,
                    })
        return res

    def button_warranty(self):
        return {
            'name': _('warranty'),
            'view_mode': 'list,form',
            'res_model': 'product.warranty',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('po_id', '=', self.id)],
        }


