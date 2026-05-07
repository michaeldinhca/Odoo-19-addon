# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, _
from odoo.exceptions import ValidationError


class QboMapUpdateMixin(models.AbstractModel):
    _name = 'qbo.map.update.mixin'
    _description = 'Abstract mixin for updating QuickBooks records'

    def update_qbo_one(self):
        if len(self) > 1:
            rec = self[:1].odoo_record
            raise ValidationError(
                _('More than one mapping is available for the %s "%s".') % (rec._description, rec.name)
            )

        self.ensure_one()

        qi = self.quickbooks_integration_id
        record = self.odoo_record

        record.ensure_one()
        record._check_qbo_requirements(qi.id)

        qb = qi.get_quickbooks_api_client()
        q = self._fetch_qbo_one_by_id(self.qbo_id, self.qbo_lib_type, client=qb)

        qbo_lib_model = record \
            .with_context(with_qbo_lib_type=self.qbo_lib_type) \
            ._prepare_qbo_api_lib_instance(qi.id, qbo_lib_model=q)

        response = self._save_qbo_one(qbo_lib_model, client=qb)

        self.update_qbo_mapping_from_response(response)

        record.unmark_for_qbo_update()

        return self.qbo_dict_body
