# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
import logging

from odoo import models, fields, _
from odoo.exceptions import ValidationError

from ....tools import parse_routes, ExtractNode
from ....quickbooks_api import QuickBooksClient, QboClassManager, catch_exception, QBO_MAX_RESULTS


_logger = logging.getLogger(__name__)


class QboMapAbstract(models.AbstractModel):
    _name = 'qbo.map.abstract'
    _description = 'Abstract proxy QuickBooks model'
    _rec_name = 'qbo_name'
    _order = 'id desc'

    _qbo_class_names = None
    _related_odoo_field = ''
    _odoo_routes = {}
    _map_routes = {}

    qbo_id = fields.Char(
        string='QuickBooks ID',
        required=True,
        readonly=True,
    )

    qbo_name = fields.Char(
        string='QuickBooks Name',
        required=True,
        readonly=True,
    )

    qbo_object = fields.Text(
        string='JSON Body',
    )

    quickbooks_integration_id = fields.Many2one(
        comodel_name='quickbooks.integration',
        string='QuickBooks Connection',
        ondelete='cascade',
        readonly=True,
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        related='quickbooks_integration_id.company_id',
        store=True,
        readonly=True,
    )

    qbo_lib_type = fields.Selection(
        selection=QboClassManager.serialize_to_selection(),
        string='QuickBooks Lib Type',
        required=True,
        readonly=True,
    )

    @property
    def job_channel(self):
        return self.sudo().env.ref('quickbooks_sync_online.channel_root_qboch_1').complete_name

    @catch_exception
    def _fetch_qbo_all(self, map_type: str, client: QuickBooksClient):
        """Fetch all objects from QuickBooks company in a single request."""
        cls = QboClassManager.get_class(map_type)

        return cls.all(qb=client)

    @catch_exception
    def _fetch_qbo_batch(self, map_type: str, position: int, client: QuickBooksClient):
        """Fetch a batch of objects from QuickBooks company."""
        cls = QboClassManager.get_class(map_type)

        return cls.filter(start_position=position, max_results=QBO_MAX_RESULTS, order_by='Id', qb=client)

    @catch_exception
    def _fetch_qbo_one_by_id(self, qbo_id: str, map_type: str, client: QuickBooksClient):
        """Fetch a single object from QuickBooks company by ID."""
        cls = QboClassManager.get_class(map_type)

        return cls.get(qbo_id, qb=client)

    @catch_exception
    def _fetch_qbo_one_with_filter(self, map_type: str, client: QuickBooksClient, **params):
        """
        Fetch a single object from QuickBooks by `params`.
        Example:: params = {'Name': 'Guido van Rossum'}
        """
        cls = QboClassManager.get_class(map_type)

        return cls.filter(qb=client, **params)

    @catch_exception
    def _fetch_qbo_by_query(self, map_type: str, condition: str, client: QuickBooksClient):
        """Fetch a batch of objects from QuickBooks company by row query."""
        cls = QboClassManager.get_class(map_type)
        query_string = "SELECT * FROM %s WHERE %s" % (cls.qbo_object_name, condition)

        return cls.query(query_string, qb=client)

    @catch_exception
    def _save_qbo_one(self, qbo_lib_model, client: QuickBooksClient):
        """Save an object to QuickBooks company."""
        return qbo_lib_model.save(qb=client)

    @catch_exception
    def _delete_qbo_by_id(self, qbo_id: str, map_type: str, client: QuickBooksClient):
        """Delete an object from intuit Company by Id."""
        cls = QboClassManager.get_class(map_type)

        record = cls()
        record.Id = qbo_id

        return record.delete(qb=client)

    def fetch_qbo_one(self):
        self.ensure_one()

        qb = self.quickbooks_integration_id.get_quickbooks_api_client()

        result = self._fetch_qbo_one_by_id(self.qbo_id, self.qbo_lib_type, client=qb)

        return result

    def fetch_qbo_one_by_pk(self, pk: str, map_type: str, qi_id: int):
        qb = self.env['quickbooks.integration'].browse(qi_id) \
            .get_quickbooks_api_client()

        result = self._fetch_qbo_one_by_id(pk, map_type, client=qb)

        return result

    def delete_qbo_one(self):
        self.ensure_one()

        qb = self.quickbooks_integration_id.get_quickbooks_api_client()

        result = self._delete_qbo_by_id(self.qbo_id, self.qbo_lib_type, client=qb)

        return result

    def delete_qbo_one_by_pk(self, pk: str, map_type: str, qi_id: int):
        qb = self.env['quickbooks.integration'].browse(qi_id) \
            .get_quickbooks_api_client()

        result = self._delete_qbo_by_id(pk, map_type, client=qb)

        return result

    def get_qbo_lib_class(self, init: bool = False):
        self.ensure_one()
        cls = QboClassManager.get_class(self.qbo_lib_type)

        if init:
            return cls()
        return cls

    def init_from_stored_json(self):
        cls = self.get_qbo_lib_class()
        return cls.from_json(self.qbo_dict_body)

    @property
    def qbo_entity_name(self):
        cls = self.get_qbo_lib_class()
        return cls.qbo_object_name

    @property
    def qbo_dict_body(self):
        self.ensure_one()
        return json.loads(self.qbo_object or '{}')

    def get_odoo_routes(self):
        return self._odoo_routes

    def get_mapping_routes(self):
        return self._map_routes

    @property
    def map_types(self):
        """Get list of the types of the linked QuickBooks lib classes."""
        return self._qbo_class_names

    @property
    def map_type(self):
        if self:
            return self.qbo_lib_type

        if len(self.map_types) == 1:
            return self.map_types[0].lower()

        raise ValidationError(
            _('No QuickBooks-type defined for the model "%s" (id=%s).' % (self._description, self.id))
        )

    def get_odoo_fk_name(self):
        return self._related_odoo_field

    @property
    def odoo_record(self):
        """Get related Odoo instance to current one."""
        return getattr(self, self.get_odoo_fk_name(), None)

    @property
    def odoo_model(self):
        """Get linked Odoo model to current one."""
        return self.browse().odoo_record

    def bind_odoo(self, odoo_id: int):
        fk_name = self.get_odoo_fk_name()
        if fk_name and odoo_id:
            self[fk_name] = odoo_id

    def extract_node(self, key_string: str, return_type: type):
        return ExtractNode.extract_raw(self.qbo_dict_body, key_string, return_type)

    def create_instance_in_odoo(self):
        """Create Odoo object from QuickBooks-map object."""
        self.ensure_one()
        record = self.odoo_record

        if record:
            return record

        if record is None:
            return None

        if not self.get_odoo_routes():
            return None

        return self._create_odoo_record()

    def fetch_resource_data_from_qbo(self, qi_id: int, map_type: str = None, job_alias_in: str = None):
        """Import all objects from QuickBooks company by the serial multiple requests."""
        qi = self.env['quickbooks.integration'].browse(qi_id)

        map_type_ = (map_type or self.map_type or '').lower()
        assert (map_type_ in [x.lower() for x in self.map_types]), (
            f'Incorrect quickbooks type for the model "{self._name}": {map_type_}.'
        )

        description_ = job_alias_in or f'{map_type_.capitalize()}s'

        return self \
            .with_context(company_id=qi.company_id.id) \
            .with_delay(
                description=f'Import {description_} from QuickBooks',
                channel=self.job_channel,
            )._fetch_resource_data_from_qbo(qi_id, map_type_)

    def _get_mapping_from_external(self, external_id: str, qi_id: int, raise_if_not_found=False):
        mapping = self.search([
            ('qbo_id', '=', str(external_id)),
            ('quickbooks_integration_id', '=', qi_id),
        ])

        if raise_if_not_found and not mapping:
            raise ValidationError(
                _('"%s": mapping not found, QboID=%s, integration=%s') % (self._description, external_id, qi_id)
            )

        return mapping

    def _parse_values_from_lib_obj(self, qbo_lib_model):
        return parse_routes(qbo_lib_model.to_dict(), self.get_mapping_routes())

    def refresh_qbo_mapping_body(self):
        """Refresh QuickBooks object from the QuickBooks company."""
        self.ensure_one()

        response = self.fetch_qbo_one()
        self.write({'qbo_object': response.to_json()})

    def update_qbo_mapping_from_response(self, qbo_lib_model):
        """Update mapping in Odoo from QuickBooks response object."""
        self.ensure_one()

        values = self._parse_values_from_lib_obj(qbo_lib_model)
        values_updated = self._adjust_mapping_values(self.quickbooks_integration_id.id, values, qbo_lib_model)

        values_updated['qbo_object'] = qbo_lib_model.to_json()

        self.write(values_updated)
        _logger.info('QuickBooks mapping "%s" (qbo_id=%s) was updated.' % (self.qbo_name, self.qbo_id))

    def create_qbo_mapping_from_response(self, qbo_lib_model, qi_id: int, odoo_id: int = None):
        mapping = self.search([
            ('qbo_id', '=', qbo_lib_model.Id),
            ('qbo_lib_type', '=', qbo_lib_model.map_type),
            ('quickbooks_integration_id', '=', qi_id),
        ], limit=1)

        if mapping:
            mapping.update_qbo_mapping_from_response(qbo_lib_model)
            mapping.bind_odoo(odoo_id)
            return mapping

        values = {
            'qbo_id': qbo_lib_model.Id,
            'qbo_lib_type': qbo_lib_model.map_type,
            'quickbooks_integration_id': qi_id,
            'qbo_object': qbo_lib_model.to_json(),
            **self._parse_values_from_lib_obj(qbo_lib_model),
        }

        values_updated = self._adjust_mapping_values(qi_id, values, qbo_lib_model)
        mapping = self.create(values_updated)
        mapping.bind_odoo(odoo_id)

        _logger.info('QuickBooks mapping "%s" (qbo_id=%s) was created.' % (mapping.qbo_name, mapping.qbo_id))
        return mapping

    def _fetch_resource_data_from_qbo(self, qi_id: int, map_type: str):
        qb = self.env['quickbooks.integration'].browse(qi_id) \
            .get_quickbooks_api_client()

        record_list = []
        while True:
            position = len(record_list) + 1
            response = self._fetch_qbo_batch(map_type, position, client=qb)

            record_list.extend(response)

            if len(response) < QBO_MAX_RESULTS:
                _logger.info('All QuickBooks records have been fetched.')
                break

        mappings = self.browse()

        for qbo_lib_model in record_list:
            mappings |= self.create_qbo_mapping_from_response(qbo_lib_model, qi_id, odoo_id=None)

        return mappings

    def _create_odoo_record(self):
        values = self._prepare_odoo_values()

        if not values:
            return self.odoo_model

        record = self.odoo_model.create(values)
        self.bind_odoo(record.id)

        return record

    def _prepare_odoo_values(self) -> dict:
        self.ensure_one()
        values = parse_routes(self.qbo_dict_body, self.get_odoo_routes())
        return self._adjust_odoo_values(values)

    def _adjust_odoo_values(self, values: dict) -> dict:
        """
        It's a hook-method for redefining during creating Odoo instance from map instance.
        Mainly for handling the temporary values after "remove dots".

        Example::
        values = {'a': {'b': 1, 'c': 2}}, 'd': 3} --> {'a': a['b'] + a['c'], 'd': 3}
        """
        self.ensure_one()
        return values

    def _adjust_mapping_values(self, qi_id: int, values: dict, qbo_lib_model) -> dict:
        """
        It's a hook-method for redefining during creating map instance from QuickBooks response.
        It's important to invoke a 'super' method to set up the 'default qbo name'.
        """
        if not values.get('qbo_name'):
            values.update(
                qbo_name=qbo_lib_model.map_type,
                qbo_object=qbo_lib_model.to_json(),
            )

        return values

    def open_formview(self):
        self.ensure_one()

        action = self.get_formview_action()
        action['target'] = 'new'

        return action
