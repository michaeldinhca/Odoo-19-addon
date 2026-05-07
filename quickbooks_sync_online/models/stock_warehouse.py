# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import models, fields


_logger = logging.getLogger(__name__)


class StockWarehouse(models.Model):
    _name = 'stock.warehouse'
    _inherit = [
        'stock.warehouse',
        'quickbooks.mapping.mixin',
        'quickbooks.export.mixin',
    ]

    qbo_mapping_ids = fields.One2many(
        comodel_name='qbo.map.department',
        inverse_name='warehouse_id',
        readonly=True,
    )

    def action_export_to_quickbooks(self):
        count = 0

        for record in self:
            company = record.company_id
            qi = company.quickbooks_integration
            mapping = record._get_qbo_mapping(qi.id, 'department')

            if mapping:
                count += 1
                job_kwargs = record._job_kwargs_qbo_transaction(map_type='department', update=True)
                record._mark_qbo_failed_jobs_as_cancel(identity_key=job_kwargs['identity_key'])

                mapping \
                    .with_context(company_id=company.id) \
                    .with_delay(**job_kwargs).update_qbo_one()
            else:
                count += 1
                job_kwargs = record._job_kwargs_qbo_transaction(map_type='department')
                record._mark_qbo_failed_jobs_as_cancel(identity_key=job_kwargs['identity_key'])

                record \
                    .with_context(company_id=company.id) \
                    .with_delay(**job_kwargs).export_qbo_one()

        return self._raise_jobs_notification(count)

    def export_qbo_one(self):
        self.ensure_one()

        if self.is_excluded_from_qbo_sync:
            return self._get_qbo_mapping(self.quickbooks_integration.id, 'department')

        qi = self.quickbooks_integration
        self = self.with_company(qi.company_id)

        self._check_qbo_requirements(qi.id)

        qbo_lib_model = self._prepare_qbo_api_lib_instance(qi.id)
        mapping = self._export_qbo_one(qi.id, qbo_lib_model)

        return mapping

    def _prepare_qbo_api_lib_instance(self, qi_id: int, qbo_lib_model=None):
        if not qbo_lib_model:
            qbo_lib_model = self._init_qbo_lib_instance('department')

        qbo_lib_model.Active = self.active
        qbo_lib_model.Name = self.name

        return qbo_lib_model
