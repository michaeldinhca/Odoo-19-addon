# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, _


class QuickbooksExportMixin(models.AbstractModel):
    _name = 'quickbooks.export.mixin'
    _description = 'QuickBooks Export Mixin'

    @property
    def quickbooks_integration(self):
        self.ensure_one()

        if 'company_id' in self:
            company = self.company_id
        else:
            company = self.env.company

        return (company or self.env.company).quickbooks_integration

    def action_export_to_quickbooks(self, *args, **kwargs):
        raise NotImplementedError

    def export_qbo_one(self, *args, **kwargs):
        raise NotImplementedError

    def to_qbo_json(self):
        raise NotImplementedError

    def _get_condition_for_check_qbo_duplicate(self, *args, **kwargs):
        raise NotImplementedError

    def _export_qbo_one(self, qi_id: int, qbo_lib_model, odoo_bind: bool = True):
        qi = self.env['quickbooks.integration'].browse(qi_id)
        qb = qi.get_quickbooks_api_client()

        MapModel = self.map_model
        response = MapModel._save_qbo_one(qbo_lib_model, client=qb)

        mapping = MapModel.create_qbo_mapping_from_response(
            response,
            qi_id,
            odoo_id=(self.id if odoo_bind else None),
        )

        return mapping

    def _export_qbo_one_after_duplicate_check(self, qi_id: int, qbo_lib_model, odoo_bind: bool = True):
        qi = self.env['quickbooks.integration'].browse(qi_id)
        qb = qi.get_quickbooks_api_client()

        MapModel = self.map_model
        map_type = qbo_lib_model.map_type

        # 1. Check for the previously added record
        condition = self._get_condition_for_check_qbo_duplicate(qbo_lib_model)
        response_list = MapModel._fetch_qbo_by_query(map_type, condition, client=qb)

        # 2. If nothing found - call the original method
        if not response_list:
            return self._export_qbo_one(qi_id, qbo_lib_model)

        response = response_list[0]

        # 3. Create mapping
        mapping = MapModel.create_qbo_mapping_from_response(
            response,
            qi_id,
            odoo_id=(self.id if odoo_bind else None),
        )

        return mapping

    def _raise_jobs_notification(self, count: int):
        if count:
            message = _('Export Jobs were created')
        else:
            message = _('No export jobs were created. The records were filtered out or not allowed to export.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'success' if count else 'warning',
                'sticky': False,
            }
        }
