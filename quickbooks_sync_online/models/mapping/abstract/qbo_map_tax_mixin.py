# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import models, _

from ....tools import TaxSuiter


_logger = logging.getLogger(__name__)


class QboMapTaxMixin(models.AbstractModel):
    _name = 'qbo.map.tax.mixin'
    _description = 'QuickBooks Map Tax Mixin'

    def apply_taxes_from_intuit(self):
        raise NotImplementedError

    def _parse_map_tax_ids(self, qi_id: int, tax_detail: list):
        """Parse QuickBooks taxes from `qbo_lib_model`. Mainly for `sale.order` and `account.move`.'"""
        tax_qbo_ids = []

        if not tax_detail:
            return self.env['qbo.map.tax']

        for rec in tax_detail.TaxLine:
            # TODO: Currently we are handling only `percent based` taxes
            tax_value = rec.TaxLineDetail.TaxRateRef.value
            if rec.Amount and rec.TaxLineDetail.PercentBased:
                tax_qbo_ids.append(tax_value)
            else:
                _logger.warning(
                    'QuickBooks: non percent-based external tax "%s" was skipped (%s)',
                    tax_value,
                    self._description,
                )

        MapTax = self.env['qbo.map.tax']
        map_ids = MapTax.browse()

        for external_id in tax_qbo_ids:
            map_id = MapTax._get_mapping_from_external(external_id, qi_id, raise_if_not_found=True)
            map_ids |= map_id

        return map_ids

    def _prepare_map_lines(self, qbo_lib_model) -> list:
        self.ensure_one()

        def extract(dict_, attr):
            return dict_.get(attr, {}).get('value', False)

        MapTax = self.env['qbo.map.tax']
        MapProduct = self.env['qbo.map.product']
        qi_id = self.quickbooks_integration_id.id

        tax_router = TaxSuiter(qbo_lib_model).get_fit_taxes()

        values_list = []
        for line in qbo_lib_model.Line:
            line_datail = getattr(line, 'SalesItemLineDetail', False)

            if not line_datail:
                continue

            if not isinstance(line_datail, dict):
                line_datail = line_datail.to_dict()

            # 1. Find product
            external_pr_id = extract(line_datail, 'ItemRef')
            map_product = MapProduct._get_mapping_from_external(external_pr_id, qi_id, raise_if_not_found=True)

            assert len(map_product) == 1, _('Expected single mapping for product "%s".') % external_pr_id

            # 2. Find taxes
            qbo_tax_ids = tax_router.get(line.LineNum, [])
            if not qbo_tax_ids:
                map_tax_ids = qbo_tax_ids
            else:
                map_tax = MapTax.browse()
                for external_tax_id in qbo_tax_ids:
                    map_id = MapTax._get_mapping_from_external(external_tax_id, qi_id, raise_if_not_found=True)

                    assert len(map_id) == 1, _('Expected single mapping for tax "%s".') % external_tax_id

                    map_tax |= map_id

                map_tax_ids = map_tax.ids

            values_list.append({
                'line_num': line.LineNum,
                'item_map_id': map_product.id,
                'tax_class': extract(line_datail, 'TaxClassificationRef'),
                'tax_code': extract(line_datail, 'TaxCodeRef'),
                'tax_map_ids': [(6, 0, map_tax_ids)],
            })

        return values_list
