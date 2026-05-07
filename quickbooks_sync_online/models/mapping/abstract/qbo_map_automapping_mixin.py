# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from copy import deepcopy
from collections import defaultdict

from odoo import models, _


SUMMARY = {
    'mapped': '- %s records were mapped:\n',
    'skipped': '- %s records already had map objects and were skipped:\n',
    'duplicated': '- %s records have multiple duplicates. Make manual mapping for:\n',
    'created': '- %s records were created.\n',
    'to_create': '- %s records have to be created manually, afterwards they might be mapped:\n',
}


class QboMapAutomappingMixin(models.AbstractModel):
    _name = 'qbo.map.automapping.mixin'
    _description = 'Abstract mixin for automapping QuickBooks records'

    def try_to_map(self, do_create=True, summary=True):
        summary_dict = defaultdict(set)
        to_create_set = set()

        for rec in self:
            rec_info = (rec.qbo_id, rec.qbo_name)
            if rec.odoo_record:
                summary_dict['skipped'].add(rec_info)
                continue

            for domain in rec._update_odoo_search_domain():
                eq_object = rec._perform_odoo_search(domain)

                if len(eq_object) == 1:
                    mapping = eq_object._get_qbo_mapping(rec.quickbooks_integration_id.id, rec.qbo_lib_type)
                    if mapping:
                        summary_dict['skipped'].add(rec_info)
                    else:
                        rec.bind_odoo(eq_object.id)
                        summary_dict['mapped'].add(rec_info)

                    to_create_set.discard(rec.id)
                    summary_dict['created'].discard(rec_info)
                    break

                if len(eq_object) > 1:
                    summary_dict['duplicated'].add(rec_info)
                    break

                if do_create:
                    to_create_set.add(rec.id)
                    summary_dict['created'].add(rec_info)
                else:
                    summary_dict['to_create'].add(rec_info)

        for rec_id in to_create_set:
            odoo_instance = self.browse(rec_id)._create_odoo_record()

            if not odoo_instance:
                map_record = self.filtered(lambda r: r.id == rec_id)
                rec_info = (map_record.qbo_id, map_record.qbo_name)
                summary_dict['created'].discard(rec_info)

        if not summary:
            return True

        ordered_dict = self._order_summary_dict(summary_dict)

        return self.env['quickbooks.help.wizard'].create_and_run_as_text(
            _('Mapping Information'),
            self._format_summary_map_info(ordered_dict),
        )

    def _update_odoo_search_domain(self):
        """
        Hook method for defining right domain in during 'Map by Name' method.
        Returns list of domains for several attempts to match current record.
        """
        return [
            [('name', '=', self.qbo_name)],
        ]

    def _perform_odoo_search(self, domain):
        return self.odoo_model.search(domain)

    @staticmethod
    def _format_summary_map_info(dct):
        info = ''
        for key, values_set in dct.items():
            items = [' ' * 8 + '. '.join(val) for val in values_set]
            info += SUMMARY.get(key, '- %s') % len(values_set) + '\n'.join(items) + '\n\n'
        return info

    @staticmethod
    def _order_summary_dict(def_dict):
        """First sets the 'matched' records and removes the dict keys where the values are empty."""
        ordered_dict = {}
        if 'mapped' in def_dict:
            mapped_ids = deepcopy(def_dict['mapped'])
            ordered_dict['mapped'] = mapped_ids
            del def_dict['mapped']

            for key, items in def_dict.items():
                items -= mapped_ids
                if items:
                    ordered_dict[key] = items
        else:
            ordered_dict = dict(def_dict)
        return ordered_dict
