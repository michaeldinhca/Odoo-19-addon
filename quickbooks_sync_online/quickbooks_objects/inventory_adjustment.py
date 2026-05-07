# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

_logger = logging.getLogger(__name__)

try:
    from quickbooks.objects.base import (
        Ref,
        QuickbooksBaseObject,
        QuickbooksManagedObject,
        QuickbooksTransactionEntity,
    )
except (ImportError, IOError) as ex:
    _logger.error(ex)


class ItemAdjustmentLineDetail(QuickbooksBaseObject):
    """
    QuickBooks definition: Provides details for a line item of type ItemAdjustmentLineDetail.
    """

    class_dict = {
        'ItemRef': Ref,
    }

    def __init__(self):
        super(ItemAdjustmentLineDetail, self).__init__()

        self.ItemRef = None
        self.QtyDiff = None


class InventoryAdjustmentLine(QuickbooksBaseObject):
    """
    QuickBooks definition: Describes the details of the line item for an inventory adjustment.
    """

    class_dict = {
        'ItemAdjustmentLineDetail': ItemAdjustmentLineDetail,
    }

    def __init__(self):
        super(InventoryAdjustmentLine, self).__init__()

        self.ItemAdjustmentLineDetail = None
        self.DetailType = 'ItemAdjustmentLineDetail'

    def item_info(self):
        return {
            'item_ref': self.ItemAdjustmentLineDetail.ItemRef.value,
            'qty_diff': self.ItemAdjustmentLineDetail.QtyDiff,
        }


class InventoryAdjustment(QuickbooksManagedObject, QuickbooksTransactionEntity):
    """
    QuickBooks definition: The InventoryAdjustment entity represents adjustments to inventory quantities.
    Basically the python-quickbooks library has no InventoryAdjustment entity, so we need to create our own
    and integrate it with the library.
    """

    qbo_object_name = 'InventoryAdjustment'

    class_dict = {
        'AdjustAccountRef': Ref,
    }

    list_dict = {
        'Line': InventoryAdjustmentLine,
    }

    def __init__(self):
        super(InventoryAdjustment, self).__init__()

        self.AdjustAccountRef = None
        self.DocNumber = ''
        self.TxnDate = ''
        self.PrivateNote = ''
        self.Line = []

    def __str__(self):
        return f'{self.qbo_object_name}({self.Id}/{self.DocNumber})'

    @property
    def has_payload(self):
        return len(self.Line) > 0

    @property
    def private_note_verbose(self):
        return f'{self.PrivateNote} (size={len(self.Line)})'

    def add_line(self, qbo_id: str, qty_diff: int) -> None:
        self.Line.append(
            {
                'DetailType': 'ItemAdjustmentLineDetail',
                'ItemAdjustmentLineDetail': {
                    'QtyDiff': int(qty_diff),
                    'ItemRef': {
                        'value': str(qbo_id),
                    }
                }
            }
        )
