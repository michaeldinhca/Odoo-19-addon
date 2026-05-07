# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import fields, models, _
from odoo.exceptions import ValidationError

from ..quickbooks_api import QboDuplicateNameError
from .mapping.qbo_map_product import ODOO_CATEGORY_LABEL


_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    _name = 'product.category'
    _inherit = [
        'product.category',
        'quickbooks.mapping.mixin',
        'quickbooks.export.mixin',
    ]

    qbo_mapping_ids = fields.One2many(
        comodel_name='qbo.map.product',
        inverse_name='category_id',
        readonly=True,
    )
    qbo_detailed_type = fields.Selection(
        selection=lambda self: self._get_qbo_product_types(),
        string='To QuickBooks Product Type',
        help='The current category will be exported to QuickBooks as a product with this type '
             'in accordance to QuickBooks setting "Sync Products as Category".',
    )

    @property
    def map_type(self):
        return self.env['qbo.map.product'].map_type

    @property
    def qbo_detailed_type_is_inventory(self):
        return self.qbo_detailed_type == 'Inventory'

    def _get_qbo_product_types(self):
        return [
            ('NonInventory', 'Consumable'),
            ('Service', 'Service'),
            ('Inventory', 'Storable Product'),
        ]

    def _get_condition_for_check_qbo_duplicate(self, qbo_lib_model):
        return f"Name = '{qbo_lib_model.Name}'"

    def _get_qbo_mapping(self, qi_id: int, map_type: str):
        mappings = super(ProductCategory, self)._get_qbo_mapping(qi_id, map_type)
        return mappings.filtered(lambda r: r.category_id.id == self.id)

    def action_export_to_quickbooks(self):
        company, count = self.env.company, 0
        qi = company.quickbooks_integration

        for record in self.with_context(company_id=company.id):
            mapping = record._get_qbo_mapping(qi.id, 'item')

            if mapping:
                count += 1
                job_kwargs = record._job_kwargs_qbo_transaction(map_type='item', update=True, job_alias_out='product')
                record._mark_qbo_failed_jobs_as_cancel(identity_key=job_kwargs['identity_key'])

                mapping.with_delay(**job_kwargs).update_qbo_one()
            else:
                count += 1
                job_kwargs = record._job_kwargs_qbo_transaction(map_type='item', job_alias_out='product')
                record._mark_qbo_failed_jobs_as_cancel(identity_key=job_kwargs['identity_key'])

                record.with_delay(**job_kwargs).export_qbo_one(qi.id)

        return self._raise_jobs_notification(count)

    def export_qbo_one(self, qi_id: int):
        self.ensure_one()

        if self.is_excluded_from_qbo_sync:
            return self._get_qbo_mapping(qi_id, 'item')

        qi = self.env['quickbooks.integration'].browse(qi_id)
        self = self.with_company(qi.company_id)

        self._check_qbo_requirements(qi_id)

        qbo_lib_model = self._prepare_qbo_api_lib_instance(qi_id)

        try:
            mapping = self._export_qbo_one(qi_id, qbo_lib_model, odoo_bind=False)
        except QboDuplicateNameError:
            mapping = self._export_qbo_one_after_duplicate_check(qi_id, qbo_lib_model, odoo_bind=False)

        mapping.category_id = self.id  # Link category instead of a product

        return mapping

    def _prepare_qbo_api_lib_instance(self, qi_id: int, qbo_lib_model=None):
        qi = self.env['quickbooks.integration'].browse(qi_id)

        if not qbo_lib_model:
            qbo_lib_model = self._init_qbo_lib_instance('item')

        qbo_lib_model.Type = self.qbo_detailed_type
        qbo_lib_model.Name = self.name
        qbo_lib_model.Description = f'{self.complete_name} {ODOO_CATEGORY_LABEL}'
        qbo_lib_model.PurchaseDesc = self.complete_name or ''

        if self.qbo_detailed_type_is_inventory:
            qbo_lib_model.QtyOnHand = 0
            qbo_lib_model.TrackQtyOnHand = True
            qbo_lib_model.InvStartDate = str(qi.auto_export_cut_off_date)

            inventory_asset = self.property_stock_valuation_account_id \
                or qi.get_qbo_default_stock_valuation_account()

            inventory_asset_rel = inventory_asset.get_qbo_related_account(qi.id)
            qbo_lib_model.AssetAccountRef = {'value': inventory_asset_rel.qbo_id}

        income_account = self.property_account_income_categ_id \
            or qi.get_qbo_default_income_account()
        income_account_rel = income_account.get_qbo_related_account(qi.id)
        qbo_lib_model.IncomeAccountRef = {'value': income_account_rel.qbo_id}

        expence_account = self.property_account_expense_categ_id \
            or qi.get_qbo_default_expense_account()
        expence_account_rel = expence_account.get_qbo_related_account(qi.id)
        qbo_lib_model.ExpenseAccountRef = {'value': expence_account_rel.qbo_id}

        return qbo_lib_model

    def _check_qbo_requirements(self, qi_id: int, *args, **kw):
        self.ensure_one()
        qi = self.env['quickbooks.integration'].browse(qi_id)

        if not self.qbo_detailed_type:
            raise ValidationError(_(
                'In order to synchronize product cateogories instead of products to QuickBooks, you need'
                'to define "QuickBooks Product Type" field on every product category. So it will be '
                'correctly synchronized to QuickBooks as either Inventory or Non-Inventory types.'
            ))

        if self.qbo_detailed_type_is_inventory:
            inventory_asset = self.property_stock_valuation_account_id \
                or qi.get_qbo_default_stock_valuation_account()

            if not inventory_asset:
                raise ValidationError(_(
                    '%s: Inventory stock valuation account is not set.' % self.display_name
                ))
            inventory_asset.get_qbo_related_account(qi_id)

        income_account = self.property_account_income_categ_id \
            or qi.get_qbo_default_income_account()

        if not income_account:
            raise ValidationError(_(
                '%s: Income account is not set.' % self.display_name
            ))
        income_account.get_qbo_related_account(qi_id)

        expence_account = self.property_account_expense_categ_id \
            or qi.get_qbo_default_expense_account()

        if not expence_account:
            raise ValidationError(_(
                '%s: Expense account is not set.' % self.display_name
            ))
        expence_account.get_qbo_related_account(qi_id)
