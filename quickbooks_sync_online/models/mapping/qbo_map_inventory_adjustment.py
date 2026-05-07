# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import pytz

from odoo import api, models, fields


class QboMapInventoryAdjustment(models.TransientModel):
    _name = 'qbo.map.inventory.adjustment'
    _inherit = 'qbo.map.abstract'
    _description = 'QuickBooks mapping: Inventory Adjustment'
    _transient_max_hours = 24 * 14

    _qbo_class_names = ('InventoryAdjustment',)

    doc_number = fields.Char(
        string='Document Number',
    )

    @api.model
    def init_mapping(self, qi_id: int):
        tz = pytz.timezone(self.env.context.get('tz') or 'UTC')
        timestamp = fields.Datetime.now().astimezone(tz).strftime('%Y-%m-%d %H:%M:%S %Z')

        return self.create({
            'qbo_id': '0',  # To be updated in the update_qbo_mapping_from_response method
            'quickbooks_integration_id': qi_id,
            'qbo_lib_type': self.map_type.lower(),
            'qbo_name': f'Export Inventory to QuickBooks [{timestamp}]',
        })

    def init_inventory(self):
        self.ensure_one()
        inventory = self.get_qbo_lib_class(init=True)

        inventory.PrivateNote = self.qbo_name
        inventory.AdjustAccountRef = {
            'value': self.quickbooks_integration_id.get_qbo_adjust_inventory_account_code(),
        }
        inventory.TxnDate = fields.Datetime.now().strftime('%Y-%m-%d')

        return inventory

    def update_qbo_mapping_from_response(self, qbo_lib_model):
        self.ensure_one()

        return self.write({
            'qbo_id': qbo_lib_model.Id,
            'qbo_object': qbo_lib_model.to_json(),
            'doc_number': qbo_lib_model.DocNumber,
            'qbo_lib_type': qbo_lib_model.map_type,
            'qbo_name': qbo_lib_model.private_note_verbose,
        })
