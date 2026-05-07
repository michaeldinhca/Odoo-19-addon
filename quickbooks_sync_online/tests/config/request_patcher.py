# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
from unittest.mock import patch
from datetime import datetime
from collections import defaultdict

from odoo.tools.safe_eval import unsafe_eval

from .storage import STORAGE
from ...quickbooks_api import QboClassManager


PATCH_LIST = [
    'item',
    'customer',
    'vendor',
    'invoice',
    'creditmemo',
    'bill',
    'vendorcredit',
    'account',
    'taxrate',
    'taxcode',
    'term',
    'paymentmethod',
    'payment',
    'salesreceipt',
]

PATCH_METHODS = [
    'all',
    'get',
    'filter',
    'save',
    'query',
    'delete',
]


class RequestPatcher:
    """Mock-class between our Odoo-server and remote Intuit cloud."""

    def __init__(self):
        """
        self.storage = {
            'account': {
                '5': '{...}',
                '12': '{...}',
            },
            'item': {
                '2': '{...}',
                '4': '{...}',
            },
            'customer': {
                '34': '{...}',
                '97': '{...}',
            },
            ...
        }
        """
        self.storage = defaultdict(lambda: defaultdict())
        self._fill_storage()

    def __call__(self, map_type):
        self.map_type = map_type.lower()

        cls = QboClassManager.get_class(self.map_type)

        self.patch_obj = f'{cls.__module__}.{cls.__name__}'
        self.intuit_obj = cls

        return self

    def __enter__(self):
        self.mock_patcher = patch.multiple(
            self.patch_obj,
            **self._prepare_patcher()
        )
        self.mock_patcher.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        return self.mock_patcher.__exit__(exc_type, exc_value, traceback)

    def _fill_storage(self):
        for map_type, list_ in STORAGE.items():
            if map_type not in PATCH_LIST:
                continue
            self.storage[map_type] = {json.loads(rec).get('Id'): rec for rec in list_}

    def _prepare_patcher(self):
        items = {}
        for method_name in PATCH_METHODS:
            if hasattr(self.intuit_obj, method_name):
                items[method_name] = unsafe_eval('self.' + '_' + method_name)
        return items

    def _get(self, qbo_id, qb=None):
        record = self.sub_repo[qbo_id]
        return self.intuit_obj.from_json(json.loads(record))

    def _filter(self, start_position='', max_results='', order_by='', qb=None, **kwargs):
        if kwargs:
            record = False
            name, value = list(kwargs.items())[0]
            for __, body in self.sub_repo.items():
                body_dict = json.loads(body)
                if body_dict.get(name) == value:
                    record = self.intuit_obj.from_json(body_dict)
                    break
            return record

        record_ids = list(self.sub_repo.keys())
        record_ids = record_ids[start_position - 1:start_position + max_results]
        return [self.intuit_obj.from_json(json.loads(self.sub_repo[rec])) for rec in record_ids]

    def _all(self, qb=None):
        record_ids = list(self.sub_repo.keys())
        return [self.intuit_obj.from_json(json.loads(self.sub_repo[rec])) for rec in record_ids]

    def _save(self, qb=None):
        max_id = max(self.sub_repo.keys(), key=lambda r: int(r)) if self.sub_repo else '0'
        next_id = str(int(max_id) + 1)
        pattern_str = STORAGE[self.map_type + '_pattern']
        object_to_save = self.intuit_obj.from_json(json.loads(pattern_str))
        object_to_save.Id = next_id
        self.storage[self.map_type][next_id] = object_to_save.to_json()
        return object_to_save

    def _query(self, row_query, qb=None):
        split_query = row_query.split()
        map_type_index = split_query.index('FROM') + 1
        map_type = split_query[map_type_index].lower()
        records_dict = self.storage.get(map_type, {})
        return [self.intuit_obj.from_json(json.loads(rec)) for rec in records_dict.values()]

    def _delete(self, qb=None):
        return True

    @property
    def sub_repo(self):
        return self.storage.get(self.map_type, {})

    def get_records_count(self, map_type):
        return len(self.storage.get(map_type, {}))

    def make_intuit_payment(self, map_invoice_id, map_invoice_type, amount, pay_type):
        Payment = QboClassManager.get_class('payment')
        pay = Payment.from_json(json.loads(STORAGE['payment_pattern']))

        max_id = max(self.storage.get('payment', {'0': ''}).keys(), key=lambda r: int(r))
        next_id = str(int(max_id) + 1)

        pay.Id = next_id
        pay.Line[0].Amount = amount
        pay.PaymentMethodRef = {'value': pay_type}
        pay.Line[0].LinkedTxn[0].TxnId = map_invoice_id
        pay.Line[0].LinkedTxn[0].TxnType = map_invoice_type
        pay.TxnDate = datetime.today().strftime('%Y-%m-%d')

        self.storage['payment'][next_id] = pay.to_json()
        return next_id
