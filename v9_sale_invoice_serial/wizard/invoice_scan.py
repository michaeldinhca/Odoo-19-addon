# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError


class invoice_scan_wizard(models.TransientModel):
    _name = "invoice.scan.wizard"
    _description = 'Invoice Scan Wizard'

    scan = fields.Char(string="Scan")

    def add_product_via_scan(self):
        lot_obj = self.env['stock.lot']
        if self.scan:
            account_move = self.env['account.move'].browse(self._context.get('active_id'))
            lot_ids = lot_obj.search([('name', '=', self.scan)])

            if not lot_ids:
                raise UserError(_(' %s Serial number is not available in system!!') % self.scan)

            line_list = []
            serial_no_list = []
            for lot_id in lot_ids:
                product = lot_id.product_id
                if not lot_id.product_qty > 0.0:
                    raise UserError(_('Stock not available with %s serial/lot number.') % self.scan)
                for line in account_move.invoice_line_ids :
                    serial_no_list.append(line.serial_no.id)

                account = product.property_account_income_id or product.categ_id.property_account_income_categ_id
                if not account:
                    raise UserError(_('Please define income account for this product: "%s" (id:%d) - or for its category: "%s".') %
                        (product.name,product.id,product.categ_id.name))
        
                fpos = account_move.fiscal_position_id or account_move.partner_id.property_account_position_id

                if fpos:
                    account = fpos.map_account(account)
                if lot_id.id in serial_no_list:
                    self.scan = ''
                    raise UserError(_('This Serial Number/Lot Is Already In Sale Order Line!!'))
                else :
                    if lot_id.product_qty > 0.0:
                        values = {
                            'name': product and product.display_name or "",
                            'move_id': account_move.id or False,
                            'account_id': account.id or False,
                            'price_unit': product.product_tmpl_id.list_price or 0.0,
                            'quantity': lot_id.product_qty,
                            'product_uom_id': product and product.product_tmpl_id and product.product_tmpl_id.uom_id and product.product_tmpl_id.uom_id.id or False,
                            'product_id': product and product.id or False,
                            'tax_ids': [(6, 0, product.taxes_id.ids)],
                            'serial_no': lot_id.id or False,
                        }
                        line_list.append((0, 0, values))
            account_move.invoice_line_ids = line_list
            self.scan = False

