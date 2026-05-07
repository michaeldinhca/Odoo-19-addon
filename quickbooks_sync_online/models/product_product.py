# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import fields, models, _
from odoo.exceptions import ValidationError

from .mapping.qbo_map_product import OPTIONS_PATTERN
from ..quickbooks_api import QboDuplicateNameError, QBO_MAX_RESULTS


_logger = logging.getLogger(__name__)

TRACK_FIELDS_PRODUCT = [
    'name', 'default_code', 'description_sale', 'description_purchase', 'list_price',
    'standard_price', 'taxes_id', 'qty_available', 'type', 'is_storable',
]

SERVICE = 'service'
CONSUMABLE = 'consu'


class ProductProduct(models.Model):
    _name = 'product.product'
    _inherit = [
        'product.product',
        'quickbooks.mapping.mixin',
        'quickbooks.export.mixin',
    ]

    qbo_mapping_ids = fields.One2many(
        comodel_name='qbo.map.product',
        inverse_name='product_id',
        readonly=True,
    )

    @property
    def is_consumable_storable(self):
        return self.type == CONSUMABLE and self.is_storable

    def write(self, vals):
        result = super(ProductProduct, self).write(vals)

        if self.env.context.get('no_mark_quickbooks_update'):
            return result

        if set(TRACK_FIELDS_PRODUCT).intersection(set(vals.keys())):
            self.filtered('qbo_mapping_ids').mark_for_qbo_update()

        return result

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
            mapping = self._export_qbo_one(qi_id, qbo_lib_model)
        except QboDuplicateNameError:
            mapping = self._export_qbo_one_after_duplicate_check(qi_id, qbo_lib_model)

        self.unmark_for_qbo_update()

        return mapping

    def _prepare_qbo_api_lib_instance(self, qi_id: int, qbo_lib_model=None):
        qi = self.env['quickbooks.integration'].browse(qi_id)

        if not qbo_lib_model:
            qbo_lib_model = self._init_qbo_lib_instance('item')

        _is_first_time_export = not qbo_lib_model.Id

        qbo_lib_model.Active = self.active
        qbo_lib_model.Name = self.display_name
        qbo_lib_model.Description = self._prepare_qbo_description()
        qbo_lib_model.PurchaseDesc = self.description_purchase or ''
        qbo_lib_model.Sku = self.default_code or ''
        qbo_lib_model.UnitPrice = self.list_price
        qbo_lib_model.PurchaseCost = self.standard_price
        qbo_lib_model.Taxable = bool(self.taxes_id)

        if self.type == SERVICE:
            qbo_lib_model.Type = 'Service'
        elif self._is_qbo_storable_product(qi):
            qbo_lib_model.Type = 'Inventory'
            qbo_lib_model.TrackQtyOnHand = True

            if _is_first_time_export:
                qbo_lib_model.QtyOnHand = self.qty_available
                qbo_lib_model.InvStartDate = str(qi.auto_export_cut_off_date)
            else:
                if qi.sync_product_stock:
                    qbo_lib_model.QtyOnHand = self.qty_available

            inventory_asset = self.categ_id.property_stock_valuation_account_id \
                or qi.get_qbo_default_stock_valuation_account()

            inventory_asset_rel = inventory_asset.get_qbo_related_account(qi_id)
            qbo_lib_model.AssetAccountRef = {'value': inventory_asset_rel.qbo_id}
        else:
            qbo_lib_model.Type = 'NonInventory'

        income_account = self.property_account_income_id \
            or self.categ_id.property_account_income_categ_id \
            or qi.get_qbo_default_income_account()

        income_account_rel = income_account.get_qbo_related_account(qi_id)
        qbo_lib_model.IncomeAccountRef = {'value': income_account_rel.qbo_id}

        expence_account = self.property_account_expense_id \
            or self.categ_id.property_account_expense_categ_id \
            or qi.get_qbo_default_expense_account()

        expence_account_rel = expence_account.get_qbo_related_account(qi_id)
        qbo_lib_model.ExpenseAccountRef = {'value': expence_account_rel.qbo_id}

        return qbo_lib_model

    def _check_qbo_requirements(self, qi_id: int, *args, **kw):
        self.ensure_one()
        qi = self.env['quickbooks.integration'].browse(qi_id)

        income_account = self.property_account_income_id  \
            or self.categ_id.property_account_income_categ_id \
            or qi.get_qbo_default_income_account()

        if not income_account:
            raise ValidationError(_(
                '%s: Income account is not set.' % self.display_name
            ))
        income_account.get_qbo_related_account(qi_id)

        expence_account = self.property_account_expense_id \
            or self.categ_id.property_account_expense_categ_id \
            or qi.get_qbo_default_expense_account()

        if not expence_account:
            raise ValidationError(_(
                '%s: Expense account is not set.' % self.display_name
            ))
        expence_account.get_qbo_related_account(qi_id)

        is_storable = self._is_qbo_storable_product(qi)

        if is_storable:
            inventory_asset = self.categ_id.property_stock_valuation_account_id \
                or qi.get_qbo_default_stock_valuation_account()

            if not inventory_asset:
                raise ValidationError(_(
                    '%s: Inventory stock valuation account is not set.' % self.display_name
                ))
            inventory_asset.get_qbo_related_account(qi_id)

    def send_stock_to_qbo_batch_job(self, qi_id: int):
        _logger.info('Send products stock to QuickBooks: ids=%s' % self.ids)

        qi = self.env['quickbooks.integration'].browse(qi_id)

        # split the iterable self for batches by 100 records
        for batch in [self[i:i+QBO_MAX_RESULTS] for i in range(0, len(self), QBO_MAX_RESULTS)]:
            job_kwargs = batch._job_kwargs_send_stock_to_qbo(qi_id)

            batch._mark_qbo_failed_jobs_as_cancel(identity_key=job_kwargs['identity_key'])

            batch \
                .with_context(company_id=qi.company_id.id) \
                .with_delay(**job_kwargs).send_stock_to_qbo(qi_id)

    def send_stock_to_qbo(self, qi_id: int):
        if not self:
            return dict()

        mapping_data = dict()
        for product in self:
            product_mapping = product._get_qbo_mapping(qi_id, 'item')
            if product_mapping:
                mapping_data[product_mapping.qbo_id] = product

        records = self.env['qbo.map.product'].get_storable_products_by_ids(
            qi_id,
            list(mapping_data.keys()),
        )

        mapping = self.env['qbo.map.inventory.adjustment'].init_mapping(qi_id)
        inventory = mapping.init_inventory()

        for qbo_record in records:
            odoo_record = mapping_data[qbo_record.Id]
            qty_diff = odoo_record.qty_available - qbo_record.QtyOnHand
            if not qty_diff:
                continue

            inventory.add_line(qbo_record.Id, qty_diff)

        if not inventory.has_payload:
            mapping.unlink()

            return {
                'qbo_id': None,
                'doc_number': None,
                'qbo_name': 'No inventory adjustments to export (QtyDiff = 0)',
                'items': [],
            }

        qi = self.env['quickbooks.integration'].browse(qi_id)
        qb = qi.get_quickbooks_api_client()

        result = mapping._save_qbo_one(inventory, client=qb)

        mapping.update_qbo_mapping_from_response(result)

        return {
            'qbo_id': result.Id,
            'doc_number': result.DocNumber,
            'qbo_name': result.private_note_verbose,
            'items': [line.item_info() for line in result.Line],
        }

    def _get_condition_for_check_qbo_duplicate(self, qbo_lib_model):
        return f"Name = '{qbo_lib_model.Name}'"

    def _prepare_qbo_description(self):
        description = self.description_sale or ''

        if not self.product_template_attribute_value_ids:
            return description

        combination_name = self.product_template_attribute_value_ids._get_combination_name()
        postfix = OPTIONS_PATTERN % combination_name

        if description:
            return f'{description} {postfix}'

        return f'{self.name} {postfix}'

    def _is_qbo_storable_product(self, qi):
        if not self.is_consumable_storable:
            return False

        if qi.send_storable_product_as_consumable:
            return False

        return True

    def _job_kwargs_send_stock_to_qbo(self, qi_id: int):
        return dict(
            priority=21,
            max_retries=1,
            identity_key=f'send_stock_to_qbo-{qi_id}-{self}',
            description=f'Export Inventory to QuickBooks (size={len(self)})',
            channel=self.env['qbo.map.abstract'].job_channel,
        )

    def to_qbo_json(self):
        self.ensure_one()

        qi = self.env.company.quickbooks_integration
        mapping = self._get_qbo_mapping(qi.id, 'item')

        if mapping:
            qbo_lib_model_ = mapping.fetch_qbo_one()
            qbo_lib_model = self._prepare_qbo_api_lib_instance(qi.id, qbo_lib_model=qbo_lib_model_)
        else:
            qbo_lib_model = self._prepare_qbo_api_lib_instance(qi.id)

        return self.env['quickbooks.help.wizard'].create_and_run_as_json(
            f'DEBUG: {self.name} [{qbo_lib_model.map_type}]',
            qbo_lib_model.to_dict(),
        )
