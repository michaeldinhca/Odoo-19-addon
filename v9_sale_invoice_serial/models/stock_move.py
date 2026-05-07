# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _
from odoo.tools.float_utils import float_compare, float_round, float_is_zero
from odoo.exceptions import UserError


class stock_move(models.Model):
    _inherit = "stock.move"

    serial_no = fields.Many2one('stock.lot',string='Serial Number',domain="[('product_id', '=', product_id)]")

    def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
        self.ensure_one()
        vals = {
            'move_id': self.id,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'picking_id': self.picking_id.id,
            'company_id': self.company_id.id,
        }
        if quantity:
            rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            uom_quantity = self.product_id.uom_id._compute_quantity(quantity, self.product_uom, rounding_method='HALF-UP')
            uom_quantity = float_round(uom_quantity, precision_digits=rounding)
            uom_quantity_back_to_product_uom = self.product_uom._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
            if float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
                vals = dict(vals, quantity=uom_quantity)
            else:
                vals = dict(vals, quantity=quantity, product_uom_id=self.product_id.uom_id.id)
        package = None
        if reserved_quant:
            package = reserved_quant.package_id
            if self.serial_no:
                vals = dict(
                    vals,
                    location_id=reserved_quant.location_id.id,
                    lot_id=self.serial_no.id or False,
                    package_id=package.id or False,
                    owner_id =reserved_quant.owner_id.id or False,
                )
            else:
                vals = dict(
                    vals,
                    location_id=reserved_quant.location_id.id,
                    lot_id=reserved_quant.lot_id.id or False,
                    package_id=package.id or False,
                    owner_id=reserved_quant.owner_id.id or False,
                )
        return vals

    def _update_reserved_quantity(self, need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        """ Create or update move lines and reserves quantity from quants
            Expects the need (qty to reserve) and location_id to reserve from.
            `quant_ids` can be passed as an optimization since no search on the database
            is performed and reservation is done on the passed quants set
        """
        self.ensure_one()
        if not lot_id:
            lot_id = self.env['stock.lot']
        if not package_id:
            package_id = self.env['stock.package']
        if not owner_id:
            owner_id = self.env['res.partner']

        quants = self.env['stock.quant'].with_context(packaging_uom_id=self.packaging_uom_id)._get_reserve_quantity(
            self.product_id, location_id, need, uom_id=self.product_uom, lot_id=lot_id, package_id=package_id,
            owner_id=owner_id, strict=strict)

        taken_quantity = 0
        rounding = self.env['decimal.precision'].precision_get('Product Unit')
        # Find a candidate move line to update or create a new one.
        candidate_lines = {}
        for line in self.move_line_ids:
            if line.result_package_id or line.product_id.tracking == 'serial':
                continue
            candidate_lines[line.location_id, line.lot_id, line.package_id, line.owner_id] = line
        move_line_vals = []
        grouped_quants = {}
        # Handle quants duplication
        for quant, quantity in quants:
            if (quant.location_id, quant.lot_id, quant.package_id, quant.owner_id) not in grouped_quants:
                grouped_quants[quant.location_id, quant.lot_id, quant.package_id, quant.owner_id] = [quant, quantity]
            else:
                grouped_quants[quant.location_id, quant.lot_id, quant.package_id, quant.owner_id][1] += quantity
        for reserved_quant, quantity in grouped_quants.values():
            taken_quantity += quantity
            to_update = candidate_lines.get(
                (reserved_quant.location_id, reserved_quant.lot_id, reserved_quant.package_id, reserved_quant.owner_id))
            if to_update:
                uom_quantity = self.product_id.uom_id._compute_quantity(quantity, to_update.product_uom_id,
                                                                        rounding_method='HALF-UP')
                uom_quantity = float_round(uom_quantity, precision_digits=rounding)
                uom_quantity_back_to_product_uom = to_update.product_uom_id._compute_quantity(uom_quantity,
                                                                                              self.product_id.uom_id,
                                                                                              rounding_method='HALF-UP')
            if to_update and float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
                to_update.with_context(reserved_quant=reserved_quant).quantity += uom_quantity
            else:
                if self.product_id.tracking == 'serial' and (
                        self.picking_type_id.use_create_lots or self.picking_type_id.use_existing_lots):
                    vals_list = self._add_serial_move_line_to_vals_list(reserved_quant, quantity)
                    if vals_list:
                        move_line_vals += vals_list
                else:
                    move_line_vals.append(
                        self._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant))
        if move_line_vals:
            self.env['stock.move.line'].create(move_line_vals)
        return taken_quantity


    def _prepare_procurement_values(self):
        res = super(stock_move,self)._prepare_procurement_values()
        self.ensure_one()
        group_id = self.group_id or False
        if self.rule_id:
            if self.rule_id.group_propagation_option == 'fixed' and self.rule_id.group_id:
                group_id = self.rule_id.group_id
            elif self.rule_id.group_propagation_option == 'none':
                group_id = False
        product_id = self.product_id.with_context(lang=self._get_lang())
        date = self._get_mto_procurement_date()
        if self.location_id.warehouse_id and self.location_id.warehouse_id.lot_stock_id.parent_path in self.location_id.parent_path:
            date = self.product_id._get_dates_info(self.date, self.location_id, self.route_ids)
            if date:
                return {
                    'product_description_variants': self.description_picking and self.description_picking.replace(product_id._get_description(self.picking_type_id), ''),
                    'date_planned': date.get('date_planned'),
                    'sale_line_id': self.sale_line_id.id,
                    'date_deadline': self.date_deadline,
                    'move_dest_ids': self,
                    'route_ids': self.route_ids,
                    'warehouse_id': self.warehouse_id or self.picking_type_id.warehouse_id,
                    'priority': self.priority,
                    'orderpoint_id': self.orderpoint_id,
                    'packaging_uom_id': self.packaging_uom_id,
                }
        return res

class stock_move_line(models.Model):
    _inherit = "stock.move.line"

    def _reservation_is_updatable(self, quantity, reserved_quant):
        return False