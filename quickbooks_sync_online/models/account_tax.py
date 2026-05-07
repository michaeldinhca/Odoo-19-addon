# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models

from ..tools import expected_one


class AccountTax(models.Model):
    _inherit = 'account.tax'

    def find_qbo_taxcodes(self, qi_id: int, partner_type: str) -> set:
        if not self:
            return []

        codes = []
        for tax in self:
            tax_mapping = tax.get_qbo_tax(qi_id)
            taxcodes = tax_mapping.find_taxcodes(partner_type, raise_error=True)

            codes.append(taxcodes)

        return list(set.intersection(*(set(x) for x in codes)))

    @expected_one
    def get_qbo_tax(self, qi_id: int):
        """Get related map instance."""
        return self._get_qbo_mapping(qi_id)

    def _get_qbo_mapping(self, qi_id: int, *args, **kwargs):
        """Uses in the 'try_to_map()' method."""
        return self.env['qbo.map.tax'].search([
            ('tax_id', '=', self.id),
            ('quickbooks_integration_id', '=', qi_id),
        ])
