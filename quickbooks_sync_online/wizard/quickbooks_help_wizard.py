# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json

from odoo import fields, models


class QuickbooksHelpWizard(models.TransientModel):
    _name = 'quickbooks.help.wizard'
    _description = 'QuickBooks Help Information Wizard'

    information = fields.Text(
        string='Information',
    )

    def create_and_run_as_json(self, name: str, dict_: dict):
        record = self.create({
            'information': json.dumps(dict_, indent=8),
        })
        return record.run_wizard(name)

    def create_and_run_as_text(self, name: str, text: str):
        record = self.create({
            'information': text,
        })
        return record.run_wizard(name)

    def run_wizard(self, name: str):
        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
