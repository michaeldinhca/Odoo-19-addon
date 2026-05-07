# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import sys
import logging
from functools import wraps
from typing import Optional

from odoo.exceptions import ValidationError

from .quickbooks_objects.inventory_adjustment import InventoryAdjustment

_logger = logging.getLogger(__name__)

try:
    from intuitlib.enums import Scopes  # noqa
    from intuitlib.client import AuthClient  # noqa
    from intuitlib.exceptions import AuthClientError

    import quickbooks.objects as objects

    from quickbooks import QuickBooks
    from quickbooks.helpers import qb_datetime_format  # noqa
    from quickbooks.exceptions import QuickbooksException, AuthorizationException, ObjectNotFoundException  # noqa
except (ImportError, IOError) as ex:
    _logger.error(ex)


QBO_API_VERSION = 75  # Version of the QuickBooks API.
QBO_MAX_RESULTS = 100  # Maximum number of results to return from the API per request

BUSINESS_OBJECTS_ADDS = [
    InventoryAdjustment.qbo_object_name,
]


class QboDuplicateNameError(QuickbooksException):

    code = 6240


class QboDuplicateDocumentNumberError(QuickbooksException):

    code = 6140


class QboInvalidAccountError(QuickbooksException):

    code = 6430


def catch_exception(method):
    @wraps(method)
    def _process_request(orm_record, *args, _perform_sub_query=True, **kwargs):
        try:
            result = method(orm_record, *args, **kwargs)
        except AuthClientError as ex:
            message = (
                'QuickBooks process request: Authentication error --> %s. '
                '\nYou need to re-authenticate your QuickBooks connection.' % (ex.args and ex.args[0])
            )
            _logger.error(message, exc_info=True)
            raise ValidationError(message) from ex

        except AuthorizationException as ex:
            if _perform_sub_query:
                integration_id = kwargs['client'].quickbooks_integration_id
                qi = orm_record.env['quickbooks.integration'].browse(integration_id)
                qi._refresh_qbo_access_token()

                _logger.info('QuickBooks process request: try api-call after token refresh.')
                return _process_request(orm_record, *args, _perform_sub_query=False, **kwargs)

            message = (
                'QuickBooks process request: Authorization error: %s, %s. %s. '
                '\nYou need to re-authorize your QuickBooks connection.' % (ex.error_code, ex.message, ex.detail)
            )
            _logger.error(message, exc_info=True)
            raise ValidationError(message) from ex

        except QuickbooksException as ex:
            message = 'QuickBooks process request: %s, %s. %s.' % (ex.error_code, ex.message, ex.detail)
            _logger.error(message, exc_info=True)

            error_code = int(ex.error_code)

            if error_code == QboDuplicateNameError.code:
                raise QboDuplicateNameError(ex.message, ex.error_code, ex.detail) from ex
            elif error_code == QboDuplicateDocumentNumberError.code:
                raise QboDuplicateDocumentNumberError(ex.message, ex.error_code, ex.detail) from ex
            elif error_code == QboInvalidAccountError.code:
                raise QboInvalidAccountError(ex.message, ex.error_code, ex.detail) from ex

            raise ex

        except Exception as ex:
            message = 'QuickBooks process request: General Exception occured --> %s.' % (ex.args and ex.args[0])
            _logger.error(message, exc_info=True)
            raise ex

        return result

    return _process_request


class QuickBooksClient(QuickBooks):

    def __init__(self, *args, **kwargs):
        # There is no parent super method
        self._quickbooks_integration_id = 0

    @property
    def quickbooks_integration_id(self) -> Optional[int]:
        return self._quickbooks_integration_id

    @quickbooks_integration_id.setter
    def quickbooks_integration_id(self, value: int) -> None:
        self._quickbooks_integration_id = value

    def isvalid_object_name(self, object_name):
        if object_name in BUSINESS_OBJECTS_ADDS:
            return True
        return super().isvalid_object_name(object_name)


class QboClassMixin:

    map_type = None

    @property
    def is_customer(self):
        return self.map_type == 'customer'

    @property
    def is_vendor(self):
        return self.map_type == 'vendor'

    @property
    def is_invoice(self):
        return self.map_type == 'invoice'

    @property
    def is_bill(self):
        return self.map_type == 'bill'

    @property
    def is_creditmemo(self):
        return self.map_type == 'creditmemo'

    @property
    def is_vendorcredit(self):
        return self.map_type == 'vendorcredit'

    @property
    def is_payment(self):
        return self.map_type == 'payment'

    @property
    def is_billpayment(self):
        return self.map_type == 'billpayment'


def create_qbo_class(cls: type, mixin: type):
    new_cls = type(f'{cls.__name__}_', (cls, mixin), {})
    new_cls.map_type = cls.qbo_object_name.lower()
    return new_cls


class QboClassAggregator:
    """QuickBooks Lib class manager."""

    def __init__(self, *class_list):
        self.core = {}
        self._key_map = {}

        for cls in class_list:
            self.update_core(cls, QboClassMixin)

    def update_core(self, cls: type, mixin: type):
        cls_ = create_qbo_class(cls, mixin)
        qbo_name = cls_.qbo_object_name

        self.core[qbo_name] = cls_
        self._key_map[cls_.map_type] = qbo_name

    def get_class(self, key: str):
        original_key = self._key_map.get(key.lower())

        if original_key is not None:
            return self.core[original_key]

        return None

    def class_list(self):
        return list(self.core.values())

    def serialize_to_selection(self):
        return [(key.lower(), key) for key in self.core.keys()]


def build_qbo_class_manager() -> QboClassAggregator:
    from quickbooks.objects.companycurrency import CompanyCurrency

    class_list = [CompanyCurrency, InventoryAdjustment]

    for attr_name in dir(objects):
        # Only consider attributes that start with an alphabetic character
        if not attr_name or not attr_name[0].isalpha():
            continue

        cls = getattr(objects, attr_name)

        if isinstance(cls, type) and hasattr(cls, 'qbo_object_name'):
            class_list.append(cls)

    return QboClassAggregator(*class_list)


QboClassManager = build_qbo_class_manager()


# Add each class as a module-level attribute (for testing purposes: for unittest.mock.patch)
for cls in QboClassManager.class_list():
    setattr(sys.modules[__name__], cls.__name__, cls)

setattr(sys.modules[__name__], 'AuthClient', AuthClient)
