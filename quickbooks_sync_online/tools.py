# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
import logging
import random
import string

from dateutil import parser
from decimal import Decimal
from itertools import combinations
from collections import defaultdict, Counter, namedtuple
from copy import deepcopy
from typing import Union, Dict, List, Type

from odoo import _
from odoo.exceptions import ValidationError

from .quickbooks_api import qb_datetime_format


_logger = logging.getLogger(__name__)


TAXABLE, NON_TAXABLE = 'TAX', 'NON'

MAPPING_MENUS = {
    'account.tax': '[QuickBooks Online --> Mapping --> Taxes]',
    'account.account': '[QuickBooks Online --> Mapping --> Accounts]',
    'account.journal': '[QuickBooks Online --> Mapping --> Payment Methods / Journals]',
    'account.payment.term': '[QuickBooks Online --> Mapping --> Payment Terms]',
}


def generate_token(length=30, allowed_chars=''.join([string.ascii_letters, string.digits])):
    """Generates random CSRF token. Based on `intuitlib.tools.generate_token`."""
    return ''.join(random.choice(allowed_chars) for i in range(length))


def expected_one(method):
    def wrapper(self, *args, **kwargs):
        self.ensure_one()

        result, error = method(self, *args, **kwargs), False

        if not result:
            error = _(
                'Mappings: match %s "%s" before export please' % (self._description.lower(), self.name)
            )
        elif len(result) > 1:
            error = _(
                'Mappings: there are several map-objects %s for %s "%s". Define the only one please'
                % (result.mapped('qbo_name'), self._description.lower(), self.name)
            )

        if error:
            menu_path = MAPPING_MENUS.get(self._name, '')
            raise ValidationError('%s: %s.' % (error, menu_path))

        return result
    return wrapper


class QboCompanyInfo:

    def __init__(self, preference, company_info, currency_list):
        self._preference = preference
        self._company_info = company_info
        self._currencies = currency_list

    @property
    def name(self):
        return self._company_info.CompanyName

    @property
    def address(self):
        return self._company_info.CompanyAddr

    @property
    def country_iso(self):
        return self._company_info.Country

    @property
    def home_currency(self):
        return self._preference.CurrencyPrefs.HomeCurrency.value

    @property
    def is_us_company(self):
        return self.country_iso == 'US'

    @property
    def multi_currency_enabled(self):
        return self._preference.CurrencyPrefs.MultiCurrencyEnabled

    def get_qbo_preference(self):
        return self._preference.to_dict()

    def get_qbo_company_info(self):
        return self._company_info.to_dict()

    def get_qbo_external_currencies(self):
        return [x.to_dict() for x in self._currencies]

    def currency_codes(self):
        return [self.home_currency] + [x.Code for x in self._currencies]

    def currency_codes_str(self):
        return ', '.join(self.currency_codes())

    def address_format(self):
        return (
            f'{self.name}, {self.address}, {self.country_iso} [{self.currency_codes_str()}]'
        )

    def get_sales_custom_field(self):
        return self._preference.SalesFormsPrefs.CustomField

    def validate_country(self, country_code: str) -> bool:
        country_iso = self.country_iso

        if country_iso and len(country_iso) == 2 and country_code != country_iso:
            # TODO: `country_iso` is optional field. We really don't know exact 'len'
            return False

        return True

    def validate_home_currency(self, currency_name: str) -> bool:
        return currency_name.lower() == self.home_currency.lower()

    def validate_foreign_currency(self, foreign_currency: str) -> bool:
        codes_list_lower = [x.lower() for x in self.currency_codes()]
        return (foreign_currency or '').lower() in codes_list_lower


class ExtractNode:

    class MissedValue:
        pass

    def __init__(self, key_string: str, return_type):
        self.keys = key_string.split('.')
        self._type = return_type

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if isinstance(result, str):
                result = json.loads(result)

            data = self._extract(result, self.keys)

            if isinstance(data, ExtractNode.MissedValue):
                return self.get_default()

            return data

        return wrapper

    def _extract(self, data, key_list):
        """
        Recursively extract the value based on the provided key list
        """
        if not key_list:
            # No more keys to process, return the current data
            return data

        key, *remaining_keys = deepcopy(key_list)

        if isinstance(data, list):
            if key.isdigit():
                if int(key) < len(data):
                    # If the key is an integer and within the list bounds, continue extraction
                    return self._extract(data[int(key)], remaining_keys)

                # _logger.warning('GraphQL parse error: Index "%s" out of range', key)
                return ExtractNode.MissedValue()

            # Handle the all lists elements
            return list(filter(
                lambda x: not isinstance(x, ExtractNode.MissedValue),
                [self._extract(x, key_list) for x in data],
            ))

        if isinstance(data, dict):
            if key in data:
                return self._extract(data[key], remaining_keys)

            # _logger.warning('GraphQL parse error: Key "%s" not found', key)
            return ExtractNode.MissedValue()

        # Unknown data type (neither a list nor a dictionary)_extract
        # _logger.warning('GraphQL parse error: Expected list or dict at key "%s", got %s', key, type(data).__name__)
        return ExtractNode.MissedValue()

    def get_default(self):
        return self._type() if callable(self._type) else self._type

    @classmethod
    def extract_raw(cls, json_data : Union[str, Dict, List], key_string: str, return_type: Type):
        # 1. init instance
        # 2. invoke the __call__ method
        # 3. invoke the `wrapper` function returned from the step 2
        return cls(key_string, return_type)(lambda: json_data)()


def _parse_nodes(dict_to_parse: dict, routes: dict = None) -> dict:
    """Extract values from QuickBooks dict-object by routes."""
    data = {}
    if not routes:
        return data

    for key, (route, return_type) in routes.items():
        value = ExtractNode.extract_raw(dict_to_parse, route, return_type)
        data[key] = value

    return data


def _remove_dots(data: dict) -> dict:
    """
    Serializing values after extracting them into the 'temporary ones with the dot'.

    Example:: data` = {'a.b': 1, 'a.c': 2, 'd': 3} --> data` = {'a': {'b': 1, 'c': 2}}, 'd': 3}
    """
    cleaned_vals = {}
    for raw_field, value in data.items():
        if raw_field.count('.'):
            sub_fields = raw_field.split('.')
            current_dict = cleaned_vals
            for field in sub_fields[:-1]:
                current_dict.setdefault(field, {})
                current_dict = current_dict[field]
            current_dict[sub_fields[-1]] = value
        else:
            cleaned_vals[raw_field] = value

    return cleaned_vals


def parse_routes(dict_to_parse: dict, routes: dict = None) -> dict:
    raw_data = _parse_nodes(dict_to_parse, routes)
    return _remove_dots(raw_data)


class TaxSuiter:

    us_tax = TAXABLE
    us_non_tax = NON_TAXABLE

    def __init__(self, record):
        self._record = record
        self._lines = self._parse_product_line()
        self._taxes = self._parse_tax_detail()

    @property
    def taxes_for_all(self):
        tax_classes = [x.tax_class for x in self.lines()]
        return len(set(tax_classes)) == 1

    def lines(self):
        return [x for x in self._lines if x.taxable]

    def taxes(self):
        return [x for x in self._taxes if x.amount and x.percent_based]

    def get_fit_taxes(self):

        if self.taxes_for_all:
            tax_ids = [x.id for x in self.taxes()]

            return {
                line.id: tax_ids for line in self.lines()
            }

        tax_dict = defaultdict(list)
        priorities = self.get_priotities()

        for tax in self.taxes():

            for qty in priorities:
                if self._find_combination(tax, qty, tax_dict):
                    break

        return tax_dict

    def _find_combination(self, tax, qty, tax_dict):
        net_amount = tax.net_amount

        for combination in self.get_combination(qty):
            amount = sum([x.amount for x in combination])

            if str(amount) == net_amount:
                [tax_dict[line.id].append(tax.id) for line in combination]
                return True

        return False

    def get_combination(self, n):
        for x in combinations(self.lines(), n):
            yield x

    def get_priotities(self):
        priority_list = list(range(0, len(self.lines()) + 1))
        priority_list.sort(reverse=True)

        counter = Counter([x.tax_class for x in self.lines()])
        most_common = list(set(dict(counter).values()))
        most_common.sort(reverse=True)

        [priority_list.remove(x) for x in most_common]

        return most_common + priority_list

    def _parse_product_line(self):
        Line = namedtuple('Line', 'id amount tax_class taxable')

        def serialize(line):
            line_num = line['LineNum']
            amount = Decimal(str(line['Amount']))

            tax_class_ref = line['SalesItemLineDetail'].get('TaxClassificationRef', {}) or {}
            tax_class_ref_value = tax_class_ref.get('value', False)

            tax_code_ref = line['SalesItemLineDetail'].get('TaxCodeRef', {}) or {}
            value = tax_code_ref.get('value', False)
            taxable = value and value != self.us_non_tax

            return Line(line_num, amount, tax_class_ref_value, bool(taxable))

        product_lines = list()

        for line in self._record.Line:

            line_dict = line.to_dict()
            sale_detail = line_dict.get('SalesItemLineDetail')

            if not sale_detail or not isinstance(sale_detail, dict):
                continue

            product_lines.append(
                serialize(line_dict)
            )

        return product_lines

    def _parse_tax_detail(self):
        Tax = namedtuple('Tax', 'id amount percent_based net_amount')

        def serialize(tax):
            return Tax(
                tax.TaxLineDetail.TaxRateRef.value,
                tax.Amount,
                tax.TaxLineDetail.PercentBased,
                str(tax.TaxLineDetail.NetAmountTaxable),
            )

        tax_detail = self._record.TxnTaxDetail

        if not tax_detail:
            return list()

        return [serialize(x) for x in tax_detail.TaxLine]


def two_dicts_are_equal(dict1: dict, dict2: dict) -> bool:
    return set(tuple(dict1.items())) == set(tuple(dict2.items()))


def parse_datetime_from_str(dtime_str):
    try:
        value = parser.isoparse(dtime_str).replace(tzinfo=None)
    except Exception:
        value = False

    return value


def convert_datetime_to_str(dtime_obj):
    try:
        value = qb_datetime_format(dtime_obj)
    except Exception:
        value = False

    return value
