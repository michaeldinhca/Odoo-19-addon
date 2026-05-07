# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

import pycountry

from odoo import fields, models, tools


_logger = logging.getLogger(__name__)


class QboMapPartner(models.Model):
    _name = 'qbo.map.partner'
    _inherit = [
        'qbo.map.abstract',
        'qbo.map.update.mixin',
    ]
    _description = 'QuickBooks mapping: Customer, Vendor'

    _related_odoo_field = 'partner_id'
    _qbo_class_names = ('Customer', 'Vendor')

    _odoo_routes = {
        'active': ('Active', True),
        'name': ('DisplayName', False),
        'company_name': ('CompanyName', False),
        'email': ('PrimaryEmailAddr.Address', False),
        'phone': ('PrimaryPhone.FreeFormNumber', False),
        'website': ('WebAddr.URI', False),
        'currency_name': ('CurrencyRef.value', False),
        'comment': ('Notes', False),
        # Billing address
        'billing.city': ('BillAddr.City', False),
        'billing.street': ('BillAddr.Line1', False),
        'billing.street2': ('BillAddr.Line2', False),
        'billing.zip': ('BillAddr.PostalCode', False),
        'billing.country_id.country_code': ('BillAddr.Country', ''),
        'billing.country_id.state_name': ('BillAddr.CountrySubDivisionCode', ''),
        # Shipping address
        'shipping.city': ('ShipAddr.City', False),
        'shipping.street': ('ShipAddr.Line1', False),
        'shipping.street2': ('ShipAddr.Line2', False),
        'shipping.zip': ('ShipAddr.PostalCode', False),
        'shipping.country_id.country_code': ('ShipAddr.Country', ''),
        'shipping.country_id.state_name': ('ShipAddr.CountrySubDivisionCode', ''),
    }
    _map_routes = {
        'qbo_name': ('DisplayName', False),
    }

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Odoo Partner',
    )

    @property
    def is_customer(self):
        return self.qbo_lib_type == 'customer'

    @property
    def parent_str_id(self):
        return self.extract_node('ParentRef.value', '')  # Only for customers

    @property
    def bill_with_parent(self):
        # BillWithParent is a boolean flag that determines
        # whether a sub-customer inherits billing from its parent customer.
        return bool(self.parent_str_id and self.extract_node('BillWithParent', False))

    def fetch_resource_data_from_qbo(self, qi_id: int, *args, **kw):
        """Redefined method to fetch all map-types."""
        for map_type in self.map_types:
            super().fetch_resource_data_from_qbo(qi_id, map_type=map_type)

    def action_create_in_odoo(self):
        for record in self:
            record = record.with_context(company_id=record.company_id.id)

            odoo_record = record.partner_id
            if odoo_record:
                record.refresh_qbo_mapping_body()  # Refresh the mapping body to get the latest data before update
                odoo_record._update_addresses_from_mapping(record.id)
            else:
                record.create_instance_in_odoo()

    def create_instance_in_odoo(self):
        self.ensure_one()

        # 1. Find parent partner
        parent_id = self.parent_str_id
        if parent_id:
            odoo_parent = self.browse() \
                .search_and_create_instance_in_odoo(self.quickbooks_integration_id.id, parent_id, self.map_type)
        else:
            odoo_parent = self.env['res.partner']

        # 2. Find or create partner
        odoo_record = self._find_odoo_partner()
        if not odoo_record:
            odoo_record = self._create_odoo_partner(parent_id=odoo_parent.id)

        # 3. Bind partner to mapping
        self.bind_odoo(odoo_record.id)

        # 4. Update Odoo partner addresses
        odoo_record._update_addresses_from_mapping(self.id)

        return odoo_record

    def search_and_create_instance_in_odoo(self, qi_id: int, qbo_id: str, map_type: str):
        record = self._get_mapping_from_external(qbo_id, qi_id)

        if not record:
            qbo_lib_class = self.fetch_qbo_one_by_pk(qbo_id, map_type, qi_id)
            record = self.create_qbo_mapping_from_response(qbo_lib_class, qi_id)

        odoo_record = record.partner_id
        if not odoo_record:
            return record.create_instance_in_odoo()

        return odoo_record

    def is_intuit_taxable_customer(self):
        self.refresh_qbo_mapping_body()

        return self.qbo_dict_body.get('Taxable', False)

    def _format_to_odoo_address(self, values: dict) -> dict:
        kwargs = {}
        country_id = state_id = False

        country_code = values['country_id']['country_code']
        state_name = values['country_id']['state_name']

        if country_code:
            if len(country_code) == 3:
                kwargs['alpha_3'] = country_code
            elif len(country_code) == 2:
                kwargs['alpha_2'] = country_code
            elif country_code:
                kwargs['name'] = country_code

            py_country = pycountry.countries.get(**kwargs) if kwargs else None

            if py_country:
                country_id = self.env['res.country'].search([
                    ('code', '=', py_country.alpha_2),
                ], limit=1).id

                if country_id:
                    if len(state_name) == 2:
                        state = pycountry.subdivisions.get(code=f'{py_country.alpha_2}-{state_name}')
                        if state:
                            state_id = self.env['res.country.state'].search([
                                ('name', '=', state.name),
                                ('country_id', '=', country_id)
                            ]).id
                    elif state_name:
                        state_id = self.env['res.country.state'].search([
                            ('name', '=', state_name),
                            ('country_id', '=', country_id)
                        ]).id

        values = {
            'zip': values['zip'],
            'city': values['city'],
            'street': values['street'],
            'street2': values['street2'],
            'state_id': state_id,
            'country_id': country_id,
        }

        if all(not x for x in values.values()):
            return {}

        return values

    def _extract_currency_name(self, lower=False):
        value = self.extract_node('CurrencyRef.value', '')
        return value.lower() if lower else value

    def _adjust_odoo_values(self, values: dict) -> dict:
        result = super(QboMapPartner, self)._adjust_odoo_values(values)

        # 1. Parse name. Remove suffix and currency name.
        name = self._parse_qbo_name(result['name'], result['currency_name'])

        # 2. Parse addreses
        billing = self._format_to_odoo_address(result.pop('billing'))

        if self.extract_node('ShipAddr', dict):
            shipping = self._format_to_odoo_address(result.pop('shipping'))
        else:
            shipping = {}

        # 3. Parse currency
        currency_name = result.pop('currency_name')
        if currency_name:
            currency_id = self.env['res.currency'].search([
                ('name', '=', currency_name),
            ]).id
        else:
            currency_id = False

        # 4. Prepare update-values dictionary
        values_upd = {
            'name': name,
            'billing': billing,
            'shipping': shipping,
            'currency_id': currency_id,
            'is_company': bool(result['company_name']),
            'email': tools.email_normalize(result['email']),
        }

        # 5. Format phone numbers
        country_id = billing.get('country_id')
        if country_id:
            values_upd['phone'] = self._proxy_phone_format(result['phone'], country_id)

        # 6. Set customer/supplier rank
        if self.is_customer:
            values_upd['customer_rank'] = 1
        else:
            values_upd['supplier_rank'] = 1

        result.update(values_upd)

        return result

    def _find_odoo_partner(self):
        values = self._prepare_odoo_values()

        domain = [('name', '=', values['name'])]

        if values['email']:
            domain.append(('email', '=', values['email']))

        if values['company_name']:
            domain.append(('is_company', '=', True))
            domain.append(('company_name', '=ilike', values['company_name']))

        return self.env['res.partner'].search(domain, limit=1)

    def _create_odoo_partner(self, **kwargs) -> models.Model:
        values = self._prepare_odoo_values()

        values.pop('billing', None)
        values.pop('shipping', None)

        values.update(kwargs)

        partner = self.env['res.partner'] \
            .with_context(no_mark_quickbooks_update=True) \
            .create(values)

        _logger.info(
            'Partner "%s" created from QuickBooks object [qbo_id=%s, type=%s]',
            partner.display_name, self.qbo_id, self.qbo_lib_type,
        )
        return partner

    def _proxy_phone_format(self, phone_number: str, country_id: int) -> str:
        """Format phone number using Odoo's built-in formatter."""
        if not phone_number or not country_id:
            return phone_number

        country = self.env['res.country'].browse(country_id)

        # Use Odoo's phone formatting utility - E.164 format. ThePYPI package "phonenumbers" required.
        formatted = self._phone_format(
            number=phone_number,
            country=country,
        )

        return formatted or phone_number

    def _parse_qbo_name(self, name: str, currency_name: str):
        self.ensure_one()

        name_ = name.replace(f'({self.qbo_lib_type})', '').strip()

        if currency_name:
            name_ = name_.replace(f'[{currency_name}]', '').strip()

        return name_
