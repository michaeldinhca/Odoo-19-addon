# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import fields, models

from ..tools import two_dicts_are_equal
from ..quickbooks_api import QboDuplicateNameError


_logger = logging.getLogger(__name__)

TRACK_FIELDS_CONTACT = [
    'name', 'parent_id', 'phone', 'email',
    'country_id', 'city', 'state_id', 'street', 'street2', 'zip',
]


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = [
        'res.partner',
        'quickbooks.mapping.mixin',
        'quickbooks.export.mixin',
    ]

    qbo_mapping_ids = fields.One2many(
        comodel_name='qbo.map.partner',
        inverse_name='partner_id',
        readonly=False,
    )

    @property
    def is_a_contact_type(self):
        return self.type == 'contact'

    def get_billing_for_qb(self):
        self.ensure_one()
        record_id = self.address_get(['billing'])['billing']
        return self.browse(record_id)

    def get_shipping_for_qb(self):
        self.ensure_one()
        record_id = self.address_get(['delivery'])['delivery']
        return self.browse(record_id)

    @property
    def is_shipping_eq_billing(self):
        billing = self.get_billing_for_qb()
        shipping = self.get_shipping_for_qb()

        return two_dicts_are_equal(
            billing._format_to_qbo_address(),
            shipping._format_to_qbo_address(),
        )

    def write(self, vals):
        result = super(ResPartner, self).write(vals)

        if self.env.context.get('no_mark_quickbooks_update'):
            return result

        if set(TRACK_FIELDS_CONTACT).intersection(set(vals.keys())):
            self.filtered('qbo_mapping_ids').mark_for_qbo_update()

        return result

    def action_export_to_quickbooks(self):
        company = self.env.company
        qi = company.quickbooks_integration

        requested_types = self.env.context.get('with_qbo_partner_type')

        if not requested_types:
            return self.env['quickbooks.partner.type.wizard'] \
                .with_context(active_partner_ids=self.ids) \
                .open_form()

        count = 0
        for qbo_partner_type in requested_types.split(','):  # "customer,vendor"
            count += self._action_export_to_quickbooks(qi.id, qbo_partner_type)

        return self._raise_jobs_notification(count)

    def _action_export_to_quickbooks(self, qi_id: int, qbo_partner_type: str):
        count = 0
        qi = self.env['quickbooks.integration'].browse(qi_id)

        for record in self.with_context(company_id=qi.company_id.id).filtered(lambda x: x.is_a_contact_type):
            mapping = record._get_qbo_mapping(qi_id, qbo_partner_type)

            if mapping:
                count += 1
                job_kwargs = record._job_kwargs_qbo_transaction(map_type=qbo_partner_type, update=True)
                record._mark_qbo_failed_jobs_as_cancel(identity_key=job_kwargs['identity_key'])

                mapping.with_delay(**job_kwargs).update_qbo_one()
            else:
                count += 1
                job_kwargs = record._job_kwargs_qbo_transaction(map_type=qbo_partner_type)
                record._mark_qbo_failed_jobs_as_cancel(identity_key=job_kwargs['identity_key'])

                record.with_delay(**job_kwargs).export_qbo_one(qi_id, qbo_partner_type)

        return count

    def export_qbo_one(self, qi_id: int, qbo_partner_type: str):
        self.ensure_one()

        if self.is_excluded_from_qbo_sync:
            return self._get_qbo_mapping(qi_id, qbo_partner_type)

        # 1. Export parent if needed
        if self._need_to_export_qbo_parent(qbo_partner_type):
            parent = self.parent_id
            if not parent._get_qbo_mapping(qi_id, qbo_partner_type):
                parent.export_qbo_one(qi_id, qbo_partner_type)

        # 2. Export self
        qi = self.env['quickbooks.integration'].browse(qi_id)
        self = self.with_company(qi.company_id)

        self._check_qbo_requirements(qi_id)

        qbo_lib_model = self \
            .with_context(with_qbo_lib_type=qbo_partner_type) \
            ._prepare_qbo_api_lib_instance(qi_id)

        try:
            mapping = self._export_qbo_one(qi_id, qbo_lib_model)
        except QboDuplicateNameError:
            mapping = self._export_qbo_one_after_duplicate_check(qi_id, qbo_lib_model)

        self.unmark_for_qbo_update()

        return mapping

    def _prepare_qbo_api_lib_instance(self, qi_id: int, qbo_lib_model=None):
        qbo_lib_type = self.env.context['with_qbo_lib_type']

        if not qbo_lib_model:
            qbo_lib_model = self._init_qbo_lib_instance(qbo_lib_type)

        # 1. Set basic fields
        qbo_lib_model.Active = self.active
        qbo_lib_model.DisplayName = self._prepare_qbo_name(qbo_lib_type)
        qbo_lib_model.GivenName = self.name
        qbo_lib_model.CompanyName = self.is_company and self.commercial_partner_id.name or ''
        qbo_lib_model.PrimaryPhone = {'FreeFormNumber': self.phone or ''}
        qbo_lib_model.WebAddr = {'URI': self.website or ''}
        qbo_lib_model.CurrencyRef = {
            'value': self.env.context.get('with_currency_name') or self.currency_id.name or '',
        }
        qbo_lib_model.PrimaryEmailAddr = {'Address': self.email or ''}

        billing = self.get_billing_for_qb()
        shipping = self.get_shipping_for_qb()

        if qbo_lib_model.is_customer:  # 2. Set customer fields
            bill_with_parent_ = False

            if self._need_to_export_qbo_parent(qbo_lib_type):
                parent_mapping = self.parent_id._get_map_instance_or_raise(qi_id, qbo_lib_type)

                qbo_lib_model.Job = True  # Requires for sub-customers
                qbo_lib_model.ParentRef = {'value': parent_mapping.qbo_id}

                mapping = self._get_qbo_mapping(qi_id, qbo_lib_type)
                if mapping:
                    bill_with_parent_ = mapping.bill_with_parent
                else:
                    bill_with_parent_ = (billing == self.parent_id.get_billing_for_qb())

            if bill_with_parent_:
                qbo_lib_model.BillWithParent = True  # No billing address for sub-customers
            else:
                qbo_lib_model.BillWithParent = False
                qbo_lib_model.BillAddr = billing._format_to_qbo_address()

                # 3. Assign shipping address for both customers and vendors
                if not self.is_shipping_eq_billing:
                    qbo_lib_model.ShipAddr = shipping._format_to_qbo_address()

        else:  # 4. Set vendor fields. There is no shipping address for vendors.
            qbo_lib_model.BillAddr = billing._format_to_qbo_address()

        return qbo_lib_model

    def _get_condition_for_check_qbo_duplicate(self, qbo_lib_model):
        return f"DisplayName = '{qbo_lib_model.DisplayName}'"

    def _prepare_qbo_name(self, qbo_lib_type: str):
        name = f'{self.name} ({qbo_lib_type})'

        currency_name = self.env.context.get('with_currency_name') or self.currency_id.name
        if currency_name and not self.quickbooks_integration.currency_name_belong_odoo_company(currency_name):
            postfix = f' [{currency_name}]'

            if not name.endswith(postfix):
                name += postfix

        return name

    def _get_qbo_mapping(self, qi_id: int, map_type: str):
        mappings = super(ResPartner, self)._get_qbo_mapping(qi_id, map_type)

        if not mappings:
            return mappings

        currency_name = self.env.context.get('with_currency_name') or str(self.currency_id.name or '')

        if not currency_name:
            return mappings

        mappings_ = mappings.filtered(
            lambda x: x._extract_currency_name(lower=True) == currency_name.lower()
        )
        return mappings_

    def _format_to_qbo_address(self):
        return {
            'City': self.city or '',
            'Country': self.country_id.code or '',
            'CountrySubDivisionCode': self.state_id.name or '',
            'Line1': self.street or '',
            'Line2': self.street2 or '',
            'PostalCode': self.zip or '',
        }

    def _ensure_qbo_currency(self, rocord: models.Model):
        currency_name = rocord.currency_id.name
        if not rocord.quickbooks_integration.currency_name_belong_odoo_company(currency_name):
            return self.with_context(with_currency_name=currency_name)
        return self

    def to_qbo_json(self):
        self.ensure_one()
        ctx = {
            'with_qbo_lib_type': 'customer',
        }
        qi = self.env.company.quickbooks_integration

        # 1. Serialize Customer
        mapping_c = self._get_qbo_mapping(qi.id, 'customer')

        if mapping_c:
            qbo_lib_model_c_ = mapping_c.fetch_qbo_one()
            qbo_lib_model_c = self.with_context(**ctx) \
                ._prepare_qbo_api_lib_instance(qi.id, qbo_lib_model=qbo_lib_model_c_)
        else:
            qbo_lib_model_c = self.with_context(**ctx)._prepare_qbo_api_lib_instance(qi.id)

        # 2. Serialize Vendor
        mapping_v = self._get_qbo_mapping(qi.id, 'vendor')
        ctx = {
            'with_qbo_lib_type': 'vendor',
        }
        if mapping_v:
            qbo_lib_model_v_ = mapping_v.fetch_qbo_one()
            qbo_lib_model_v = self.with_context(**ctx) \
                ._prepare_qbo_api_lib_instance(qi.id, qbo_lib_model=qbo_lib_model_v_)
        else:
            qbo_lib_model_v = self.with_context(**ctx)._prepare_qbo_api_lib_instance(qi.id)

        return self.env['quickbooks.help.wizard'].create_and_run_as_json(
            f'DEBUG: {self.name}',
            {
                'CUSTOMER JSON': qbo_lib_model_c.to_dict(),
                'VENDOR JSON': qbo_lib_model_v.to_dict(),
            },
        )

    def _update_addresses_from_mapping(self, mapping_id: int):
        self.ensure_one()

        mapping = self.env['qbo.map.partner'].browse(mapping_id)
        values = mapping._prepare_odoo_values()

        billing_input = values['billing']
        shipping_input = values['shipping']

        if billing_input:
            if not mapping.bill_with_parent:
                if self._has_empty_address():
                    # If the partner has an empty address, write the billing address to the partner
                    self.with_context(no_mark_quickbooks_update=True).write(billing_input)
                elif self._current_address_match_dict(billing_input):
                    # If the billing address is the same as the current address, do nothing
                    pass
                else:
                    # If the billing address is different from the current address, get or create a child address-card
                    self._get_or_create_child_address('invoice', billing_input)

        if shipping_input:
            # If the shipping address is different from the billing address, get or create a child address-card
            if not two_dicts_are_equal(shipping_input, billing_input):
                shipping = self.get_shipping_for_qb()
                # If the shipping address is different from the current address, get or create a child address-card
                if not shipping._current_address_match_dict(shipping_input):
                    self._get_or_create_child_address('delivery', shipping_input)

        return True

    def _need_to_export_qbo_parent(self, qbo_partner_type: str):
        parent = self.parent_id
        return bool(parent and not parent.is_excluded_from_qbo_sync and qbo_partner_type.lower() == 'customer')

    def _has_empty_address(self):
        return all(not self[field] for field in self._get_address_match_fields())

    def _get_address_match_fields(self):
        return ['country_id', 'state_id', 'zip', 'city', 'street', 'street2']

    def _prepare_address_match_dict(self):
        """ Prepare a dictionary of address match fields for the partner """
        result = {}
        for field in self._get_address_match_fields():
            value = self[field]
            if isinstance(value, models.Model):
                value = value.id

            result[field] = value

        return result

    def _current_address_match_dict(self, values: dict):
        self_values = self._prepare_address_match_dict()
        return two_dicts_are_equal(self_values, values)

    def _get_or_create_child_address(self, address_type: str, values: dict):
        # Reuse existing address if an identical one exists.
        address = self.with_context(active_test=False).child_ids.filtered(
            lambda x: x.type == address_type
            and self.country_id == x.country_id
        )

        domain = []

        state_id = values['state_id'] or False
        domain.append(('state_id', '=', state_id))

        street1 = values['street']
        if street1:
            domain.append(('street', '=ilike', street1))
        else:
            domain.append(('street', 'in', ['', False]))

        street2 = values['street2']
        if street2:
            domain.append(('street2', '=ilike', street2))
        else:
            domain.append(('street2', 'in', ['', False]))

        city = values['city']
        if city:
            domain.append(('city', '=ilike', city))
        else:
            domain.append(('city', 'in', ['', False]))

        zip_code = values['zip']
        if zip_code:
            domain.append(('zip', '=ilike', zip_code))
        else:
            domain.append(('zip', 'in', ['', False]))

        address = address.filtered_domain(domain)[:1]

        if address:
            if not address.active:
                address.with_context(no_mark_quickbooks_update=True).write({'active': True})
            return address

        return self.with_context(no_mark_quickbooks_update=True) \
            .create({
                'name': self.name,
                'type': address_type,
                'parent_id': self.id,
                **values,
            })
