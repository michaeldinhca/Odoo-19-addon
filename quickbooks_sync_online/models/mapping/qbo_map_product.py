# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import re

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


ODOO_CATEGORY_LABEL = '[odoo category]'
OPTIONS_PATTERN = '[options: %s]'


class QboMapProduct(models.Model):
    _name = 'qbo.map.product'
    _inherit = [
        'qbo.map.abstract',
        'qbo.map.update.mixin',
        'qbo.map.automapping.mixin',
    ]
    _description = 'QuickBooks mapping: Item'

    _related_odoo_field = 'product_id'
    _qbo_class_names = ('Item',)

    _odoo_routes = {
        'active': ('Active', True),
        'name': ('Name', ''),
        'type.type_': ('Type', ''),
        'description_sale': ('Description', ''),
        'description_purchase': ('PurchaseDesc', ''),
        'default_code': ('Sku', ''),
        'list_price': ('UnitPrice', 0),
        'standard_price': ('PurchaseCost', 0),
    }
    _map_routes = {
        'qbo_name': ('Name', ''),
        'stock_keeping_unit': ('Sku', ''),
        'description_': ('Description', ''),
    }

    stock_keeping_unit = fields.Char(
        string='Stock Keeping Unit',
        help=(
            'This is a company-defined identifier for an item or product '
            'used in tracking inventory ("Internal Reference" Odoo equivalent).'
        ),
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Odoo Product',
    )
    category_id = fields.Many2one(
        comodel_name='product.category',
        string='Product Category',
    )
    product_type = fields.Char(
        string='QuickBooks Product Type',
        compute='_compute_product_type',
    )
    variant_options = fields.Char(
        string='Options',
    )

    @api.depends('qbo_object')
    def _compute_product_type(self):
        for rec in self:
            product_type = rec.qbo_dict_body.get('Type', '')
            rec.product_type = self._convert_type_to_odoo(product_type)

    @api.depends('qbo_name', 'stock_keeping_unit')
    def _compute_display_name(self):
        for rec in self:
            value = rec.qbo_name
            if rec.stock_keeping_unit:
                value = '[%s] %s' % (rec.stock_keeping_unit, value)
            if rec.variant_options:
                value = f'{value} ({rec.variant_options})'

            rec.display_name = value

    @property
    def odoo_record(self):
        if self.category_id:
            return self.category_id
        return super().odoo_record

    def get_odoo_fk_name(self):
        if self.category_id:
            return 'category_id'
        return super().get_odoo_fk_name()

    def get_storable_products_by_ids(self, qi_id: int, ids: list) -> list:
        condition = "Id IN (%s) AND Type = 'Inventory'" % ','.join(repr(str(x)) for x in ids)
        qb = self.env['quickbooks.integration'].browse(qi_id).get_quickbooks_api_client()

        result = self.env['qbo.map.product']._fetch_qbo_by_query('item', condition, client=qb)
        return result

    def _convert_type_to_odoo(self, product_type):
        variants = dict(
            self.env['product.category']._get_qbo_product_types()
        )
        return variants.get(product_type, product_type)

    def _update_odoo_search_domain(self):
        domain_list = super()._update_odoo_search_domain()

        sku = self.stock_keeping_unit
        if sku:
            return [[('default_code', '=', sku)], *domain_list]

        domain_list[0].append(('default_code', 'in', [False, '']))
        return domain_list

    def _perform_odoo_search(self, domain):
        result = super(QboMapProduct, self)._perform_odoo_search(domain)

        variant_options = self.variant_options
        if variant_options:
            result = result.filtered(
                lambda x: x.product_template_attribute_value_ids and
                x.product_template_attribute_value_ids._get_combination_name() == variant_options
            )

        return result

    def _adjust_mapping_values(self, qi_id: int, values: dict, qbo_lib_model) -> dict:
        res = super(QboMapProduct, self)._adjust_mapping_values(qi_id, values, qbo_lib_model)

        postfix = self._parse_postfix_from_description(
            res.pop('description_', ''),
        )
        if postfix:
            res['variant_options'] = postfix

        res['qbo_name'] = self._normalize_qbo_name(
            res.get('qbo_name'),
            prefix=res.get('stock_keeping_unit'),
            postfix=postfix,
        )
        return res

    def _adjust_odoo_values(self, values):
        res = super(QboMapProduct, self)._adjust_odoo_values(values)

        if ODOO_CATEGORY_LABEL in (res.get('description_sale') or ''):
            res.clear()
            return res

        prefix = res.get('default_code')
        description = res.get('description_sale')
        postfix = self._parse_postfix_from_description(description)

        if description and postfix:
            res['description'] = description.replace(OPTIONS_PATTERN % postfix, '').strip()

        res['name'] = self._normalize_qbo_name(
            res.get('name'),
            prefix=prefix,
            postfix=postfix,
        )

        if not prefix:
            res.pop('default_code', True)

        type_ = res['type']['type_']
        if type_ == 'Service':
            res['type'] = 'service'
            res.update(
                type='service',
                categ_id=self.env.ref('product.product_category_services').id,
            )
        elif type_ == 'Inventory':
            res.update(
                type='consu',
                is_storable=True,
                categ_id=self.env.ref('product.product_category_goods').id,
            )
        elif type_ == 'NonInventory':
            res['type'] = 'consu'
        else:
            raise ValidationError(_(
                'Creation this type of product "%s" for "%s" not supported! '
                'Only "Service", "Inventory", "NonInventory"' % (type_, self.qbo_name)
            ))
        return res

    def _create_odoo_record(self):
        if self.category_id:
            raise ValidationError(_(
                'A new product may not be created from "map product category".'
            ))
        return super(QboMapProduct, self)._create_odoo_record()

    @staticmethod
    def _normalize_qbo_name(name, prefix=None, postfix=None):
        if prefix:
            prefix_pattern = f'[{prefix}]'

            if name.startswith(prefix_pattern):
                name = name.replace(prefix_pattern, '').strip()

        if postfix:
            postfix_pattern = f'({postfix})'
            name = name.replace(postfix_pattern, '').strip()

        return name

    @staticmethod
    def _parse_postfix_from_description(description):
        search_ = list()
        if description:
            search_ = re.findall(r'\[options: (.+)\]', description)
        return search_ and search_[0] or ''
