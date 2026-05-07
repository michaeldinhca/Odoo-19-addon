# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError

from ...quickbooks_api import QboClassManager


_logger = logging.getLogger(__name__)


MODELS_TO_EXPORT = {  # (name : queue-job priority)
    'stock.warehouse': 11,
    'res.partner': 13,
    'product.category': 15,
    'product.product': 17,
    'account.move': 19,
    'account.payment': 21,
}

ERROR_MESSAGES = {
    'failed': (
        'QuickBooks Job Error! '
        'More details on the "QuickBooks Online" tab.'
    ),
    'rejected': (
        'QuickBooks Job has not been created! '
        'More details on the "QuickBooks Online" tab.'
    ),
}


class QuickbooksMappingMixin(models.AbstractModel):
    _name = 'quickbooks.mapping.mixin'
    _description = 'QuickBooks Mapping Mixin'

    is_qbo_sync_done = fields.Boolean(
        string='QuickBooks Synced',
        compute='_compute_qbo_sync_done',
    )
    is_excluded_from_qbo_sync = fields.Boolean(
        string='Exclude from QuickBooks Sync',
        copy=False,
    )
    is_qbo_update_required = fields.Boolean(
        string='QuickBooks Update Required',
        copy=False,
    )
    qbo_mapping_ids = fields.One2many(  # To redefine in child models
        comodel_name='qbo.map.abstract',
        string='QuickBooks Mappings',
    )

    @property
    def map_model(self):
        return self.qbo_mapping_ids.browse()

    @property
    def map_types(self):
        return self.map_model.map_types

    @property
    def map_type(self):
        self.ensure_one()
        return self.map_model.map_type

    @api.depends('qbo_mapping_ids')
    def _compute_qbo_sync_done(self):
        qi = self.env.company.quickbooks_integration

        for rec in self:
            rec.is_qbo_sync_done = bool(rec.qbo_mapping_ids.filtered(lambda r: r.quickbooks_integration_id == qi))

    def _prepare_qbo_api_lib_instance(self, *args, **kwargs):
        raise NotImplementedError

    def _init_qbo_lib_instance(self, map_type):
        return QboClassManager.get_class(map_type)()

    def _get_qbo_mapping(self, qi_id: int, map_type: str):
        return self.qbo_mapping_ids \
            .filtered(
                lambda r: r.qbo_lib_type == map_type.lower() and r.quickbooks_integration_id.id == qi_id
            )

    def _get_map_instance_or_raise(self, qi_id: int, map_type: str, raise_if_not_found: bool = True):
        self.ensure_one()
        instance = self._get_qbo_mapping(qi_id, map_type)

        if len(instance) > 1:
            raise ValidationError(_(
                'More than one mapping is available for "%s". '
                'It must be the only one in the current users company "%s".'
                % (self.name, self.env['quickbooks.integration'].browse(qi_id).name)
            ))
        if not instance and raise_if_not_found:
            raise ValidationError(_(
                'Firstly you should perform export of "%s".' % self.name
            ))

        return instance

    def _check_qbo_requirements(self, *args, **kw):
        """Hook method for redefining."""
        return True

    def mark_excluded_from_qbo_sync(self):
        self.with_context(no_mark_quickbooks_update=True).write({
            'is_excluded_from_qbo_sync': True,
        })

    def unmark_excluded_from_qbo_sync(self):
        self.with_context(no_mark_quickbooks_update=True).write({
            'is_excluded_from_qbo_sync': False,
        })

    def mark_for_qbo_update(self):
        self.with_context(no_mark_quickbooks_update=True).write({
            'is_qbo_update_required': True,
        })

    def unmark_for_qbo_update(self):
        self.with_context(no_mark_quickbooks_update=True).write({
            'is_qbo_update_required': False,
        })

    def _job_kwargs_qbo_transaction(self, map_type: str = False, update: bool = False, job_alias_out: str = None):
        priotiry = MODELS_TO_EXPORT[self._name]
        map_type_ = map_type or self.map_type

        name_ = job_alias_out or map_type_.lower()
        description = f'Export {name_} "{self.display_name}" to QuickBooks'

        if update:
            description = f'{description} (update action)'

        return dict(
            max_retries=1,
            priority=priotiry,
            identity_key=f'qbo_export_{map_type_.lower()}-{self.env.company.id}-{self}',
            description=description,
            channel=self.env['qbo.map.abstract'].job_channel,
        )

    def _mark_qbo_failed_jobs_as_cancel(self, identity_key=None):
        if not identity_key:
            identity_key = self._job_kwargs_qbo_transaction()['identity_key']

        return self.env['queue.job'].cancel_failed_jobs_by_identity_key(identity_key)

    def open_current_object(self):
        """
        Open full form of current object.
        There is a standard method 'get_formview_action()',
        but it may be overriden by someone for custom view.
        """
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'self',
        }
