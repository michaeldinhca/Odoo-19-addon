# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _


class account_invoice_line(models.Model):
    _inherit = "account.move.line"

    serial_no = fields.Many2one('stock.lot', string='Serial Number',domain="[('product_id', '=', product_id)]")

