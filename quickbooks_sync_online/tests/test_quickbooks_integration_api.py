# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from datetime import datetime, date
from unittest.mock import patch

from odoo.tests import tagged
from odoo.exceptions import ValidationError, UserError

from .config.request_patcher import RequestPatcher
from .config.intuit_case import (
    IMPORT_MODELS_BY_BATCH,
    request_client,
    QuickbooksInit,
)

from ..tools import TAXABLE, NON_TAXABLE


PRODUCT = 'item'
VENDOR = 'vendor'
CUSTOMER = 'customer'
INVOICE = 'invoice'
CREDIT_NOTE = 'creditmemo'
BILL = 'bill'
PAYMENT = 'payment'
SALE_ORDER = 'salesreceipt'


@tagged('-at_install', '-standard', 'post_install', 'qbo_test_api')
class TestQuickbooksIntegrationAPI(QuickbooksInit):

    def setUp(self):
        super(TestQuickbooksIntegrationAPI, self).setUp()

        self.patcher = RequestPatcher()

        self._set_up_connection()
        self._fill_the_dadabase()
        self._load_xml('init_accounts.xml')
        self._set_ir_defaults()
        self.map_default_company_stock_account()

    def _set_ir_defaults(self):
        self.env['ir.default'].set(
            'product.category',
            'property_account_expense_categ_id',
            self.env.ref('quickbooks_sync_online.a_expense').id,
            company_id=self.company.id,
        )
        self.env['ir.default'].set(
            'product.category',
            'property_account_income_categ_id',
            self.env.ref('quickbooks_sync_online.a_expense').id,
            company_id=self.company.id,
        )
        self.env['ir.default'].set(
            'product.category',
            'property_stock_valuation_account_id',
            self.env.ref('quickbooks_sync_online.stk').id,
            company_id=self.company.id,
        )
        self.env['ir.default'].set(
            'res.partner',
            'property_account_payable_id',
            self.env.ref('quickbooks_sync_online.a_pay').id,
            company_id=self.company.id,
        )

    @patch(request_client)
    def _fill_the_dadabase(self, *args):
        for _name in IMPORT_MODELS_BY_BATCH:
            model_id = self.env[_name]
            for map_type in model_id.map_types:
                with self.patcher(map_type):
                    model_id._fetch_resource_data_from_qbo(self.qi.id, map_type)

    def create_tax(self):
        return self.env['account.tax'].create({
            'name': '15% Test',
            'type_tax_use': 'sale',
            'amount': 15,
            'tax_group_id': self.env.ref('quickbooks_sync_online.tax_group_15_test').id,
            'company_id': self.company.id,
            'amount_type': 'percent',
        })

    def proxy_models(self):
        return [self.env[name] for name in IMPORT_MODELS_BY_BATCH]

    def map_all_accounts(self):
        self.map_default_company_stock_account()

        intuit_accounts = self.env['qbo.map.account'].search([
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        intuit_accounts.try_to_map(do_create=False)
        return intuit_accounts.filtered('account_id')

    def map_cost_of_gods_sold(self):
        account = self.env['qbo.map.account'].search([
            ('qbo_name', '=', 'Cost of Goods Sold (test)'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        account.try_to_map(do_create=False)

    def map_sales_income(self):
        account = self.env['qbo.map.account'].search([
            ('qbo_name', '=', 'Sales of Product Income (test)'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        account.try_to_map(do_create=False)

    def map_default_company_stock_account(self):
        self.qi.write({
            'qi_default_stock_valuation_account_id': self.env.ref('quickbooks_sync_online.stk').id,
        })

    def map_inventory_asset(self):
        account = self.env['qbo.map.account'].search([
            ('qbo_name', '=', 'Inventory Asset (test)'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        account.try_to_map(do_create=False)

    def map_account_payable(self):
        account = self.env['qbo.map.account'].search([
            ('qbo_name', '=', 'Accounts Payable (A/P) (test)'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        account.try_to_map(do_create=False)

    def map_payment_defaults(self):
        self.qi.write({
            'qi_default_journal_id': self.env.ref('quickbooks_sync_online.bank_journal').id,
        })
        cash_method = self.env['qbo.map.payment.method'].search([
            ('qbo_id', '=', '1'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        cash_method.write({
            'journal_id': self.env.ref('quickbooks_sync_online.cash_journal').id,
        })

    def test_import_count(self):
        for model_id in self.proxy_models():
            for map_type in model_id.map_types:
                records_count = model_id.search_count([
                    ('qbo_lib_type', '=', map_type),
                    ('quickbooks_integration_id', '=', self.qi.id),
                ])
                remote_records_count = self.patcher.get_records_count(map_type)
                self.assertEqual(records_count, remote_records_count)

    def test_map_or_create_inventory_product_from_map_object(self):
        inventory_214 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '214'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(inventory_214.qbo_name, 'Flag_AWSECrfaew')
        self.assertEqual(inventory_214.display_name, '[8976] Flag_AWSECrfaew')
        self.assertEqual(inventory_214.stock_keeping_unit, '8976')
        self.assertEqual(inventory_214.product_id.id, False)
        self.assertEqual(inventory_214.qbo_lib_type, PRODUCT)

        inventory_214._create_odoo_record()
        product1 = inventory_214.product_id

        self.assertTrue(product1.active)
        self.assertEqual(product1.name, 'Flag_AWSECrfaew')
        self.assertEqual(product1.type, 'consu')
        self.assertTrue(product1.is_storable)
        self.assertEqual(product1.description_sale, 'Sale Description')
        self.assertEqual(product1.description_purchase, '')
        self.assertEqual(product1.default_code, '8976')
        self.assertEqual(product1.list_price, 90)
        self.assertEqual(product1.standard_price, 78)

        # Another one
        inventory_215 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '215'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(inventory_215.qbo_name, 'Corner Desk Black_jhdrThg')
        self.assertEqual(inventory_215.display_name, '[FURN_1118_1] Corner Desk Black_jhdrThg')
        self.assertEqual(inventory_215.stock_keeping_unit, 'FURN_1118_1')
        self.assertEqual(inventory_215.product_id.id, False)
        self.assertEqual(inventory_215.qbo_lib_type, PRODUCT)

        inventory_215._create_odoo_record()
        product2 = inventory_215.product_id

        self.assertTrue(product2.active)
        self.assertEqual(product2.name, 'Corner Desk Black_jhdrThg')
        self.assertEqual(product2.type, 'consu')
        self.assertTrue(product1.is_storable)
        self.assertEqual(product2.description_sale, '')
        self.assertEqual(product2.description_purchase, '')
        self.assertEqual(product2.default_code, 'FURN_1118_1')
        self.assertEqual(product2.list_price, 85)
        self.assertEqual(product2.standard_price, 78)

        # Unmap models and create odoo product copy
        records = inventory_214 + inventory_215
        records.write({'product_id': False})
        product1.copy({
            'name': 'Flag_AWSECrfaew',
            'default_code': '8976',
        })
        # Try to map
        records.try_to_map(summary=False)
        # Check mapping result
        self.assertEqual(inventory_214.product_id.id, False)
        self.assertEqual(inventory_215.product_id.id, product2.id)

    def test_map_or_create_consumable_product_from_map_object(self):
        consum_126 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '126'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(consum_126.qbo_name, 'Table_Ert254g')
        self.assertEqual(consum_126.display_name, '[89977897] Table_Ert254g')
        self.assertEqual(consum_126.stock_keeping_unit, '89977897')
        self.assertEqual(consum_126.product_id.id, False)
        self.assertEqual(consum_126.qbo_lib_type, PRODUCT)

        consum_126._create_odoo_record()
        product1 = consum_126.product_id

        self.assertTrue(product1.active)
        self.assertEqual(product1.name, 'Table_Ert254g')
        self.assertEqual(product1.type, 'consu')
        self.assertFalse(product1.is_storable)
        self.assertEqual(product1.description_sale, '')
        self.assertEqual(product1.description_purchase, '')
        self.assertEqual(product1.default_code, '89977897')
        self.assertEqual(product1.list_price, 99.9)
        self.assertEqual(product1.standard_price, 67.8)

        # Another one
        consum_137 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '137'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(consum_137.qbo_name, 'Another Table_Ert254g')
        self.assertEqual(consum_137.display_name, 'Another Table_Ert254g')
        self.assertEqual(consum_137.stock_keeping_unit, False)
        self.assertEqual(consum_137.product_id.id, False)
        self.assertEqual(consum_137.qbo_lib_type, PRODUCT)

        consum_137._create_odoo_record()
        product2 = consum_137.product_id

        self.assertTrue(product2.active)
        self.assertEqual(product2.name, 'Another Table_Ert254g')
        self.assertEqual(product2.type, 'consu')
        self.assertFalse(product1.is_storable)
        self.assertEqual(product2.description_sale, '')
        self.assertEqual(product2.description_purchase, 'Some purchase description..')
        self.assertEqual(product2.default_code, False)
        self.assertEqual(product2.list_price, 89)
        self.assertEqual(product2.standard_price, 0)

        # Unmap models and create odoo product copy
        records = consum_126 + consum_137
        records.write({'product_id': False})
        product1.copy({
            'name': 'Table_Ert254g',
            'default_code': '89977897',
        })
        # Try to map
        records.try_to_map(summary=False)
        # Check mapping result
        self.assertEqual(consum_126.product_id.id, False)
        self.assertEqual(consum_137.product_id.id, product2.id)

    def test_map_or_create_service_product_from_map_object(self):
        service_3 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '3'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(service_3.qbo_name, 'Concrete3_QDSVCrt')
        self.assertEqual(service_3.display_name, 'Concrete3_QDSVCrt')
        self.assertEqual(service_3.stock_keeping_unit, False)
        self.assertEqual(service_3.product_id.id, False)
        self.assertEqual(service_3.qbo_lib_type, PRODUCT)

        service_3._create_odoo_record()
        product1 = service_3.product_id

        self.assertTrue(product1.active)
        self.assertEqual(product1.name, 'Concrete3_QDSVCrt')
        self.assertEqual(product1.type, 'service')
        self.assertEqual(product1.description_sale, 'Concrete for fountain installation')
        self.assertEqual(product1.description_purchase, '')
        self.assertEqual(product1.default_code, False)
        self.assertEqual(product1.list_price, 0)
        self.assertEqual(product1.standard_price, 0)

        # Another one
        service_4 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '4'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(service_4.qbo_name, 'Design CevrTw45')
        self.assertEqual(service_4.display_name, 'Design CevrTw45')
        self.assertEqual(service_4.stock_keeping_unit, False)
        self.assertEqual(service_4.product_id.id, False)
        self.assertEqual(service_3.qbo_lib_type, PRODUCT)

        service_4._create_odoo_record()
        product2 = service_4.product_id

        self.assertTrue(product2.active)
        self.assertEqual(product2.name, 'Design CevrTw45')
        self.assertEqual(product2.type, 'service')
        self.assertEqual(product2.description_sale, 'Custom Design')
        self.assertEqual(product2.description_purchase, '')
        self.assertEqual(product2.default_code, False)
        self.assertEqual(product2.list_price, 75)
        self.assertEqual(product2.standard_price, 0)

        # Unmap models and create odoo product copy
        records = service_3 + service_4
        records.write({'product_id': False})
        product1.copy({'name': 'Concrete3_QDSVCrt'})
        # Try to map
        records.try_to_map(summary=False)
        # Check mapping result
        self.assertEqual(service_3.product_id.id, False)
        self.assertEqual(service_4.product_id.id, product2.id)

    def test_map_or_create_unsupported_type_from_map_object(self):
        category_64 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '64'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(category_64.qbo_name, 'T-Shirt Unisex')
        self.assertEqual(category_64.stock_keeping_unit, False)
        self.assertEqual(category_64.product_id.id, False)
        self.assertEqual(category_64.qbo_lib_type, PRODUCT)

        with self.assertRaises(ValidationError):
            category_64._create_odoo_record()

    def test_map_or_create_customer_from_map_object(self):
        map_customer_2 = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '2'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(map_customer_2.qbo_name, 'Bill Windsurf Display Name')
        self.assertEqual(map_customer_2.partner_id.id, False)

        map_customer_2.create_instance_in_odoo()
        customer1 = map_customer_2.partner_id

        self.assertTrue(customer1.active)
        self.assertEqual(customer1.name, 'Bill Windsurf Display Name')
        self.assertEqual(customer1.company_name, 'Bill Windsurf Company')
        self.assertEqual(customer1.email, 'surf_acesrcdfg@intuit.com')
        self.assertEqual(customer1.phone, '5555554354611')

        billing = customer1.child_ids.filtered(lambda r: r.type == 'invoice')
        self.assertFalse(bool(billing))

        self.assertEqual(customer1.city, '12 Ocean Dr.')
        self.assertEqual(customer1.country_id.name, 'United States')
        self.assertEqual(customer1.state_id.name, 'California')
        self.assertEqual(customer1.street, 'Half Moon Bay')
        self.assertEqual(customer1.street2, 'Moon bay-j')
        self.assertEqual(customer1.zip, '94213')

        shipping = customer1.child_ids.filtered(lambda r: r.type == 'delivery')
        self.assertFalse(bool(shipping))

    def test_map_or_create_vendor_from_map_object(self):
        map_vendor_30 = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '30'),
            ('qbo_lib_type', '=', VENDOR),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertEqual(map_vendor_30.qbo_name, 'Books by Bessie Display Name')
        self.assertEqual(map_vendor_30.partner_id.id, False)

        map_vendor_30.create_instance_in_odoo()
        vendor1 = map_vendor_30.partner_id

        self.assertTrue(vendor1.active)
        self.assertEqual(vendor1.name, 'Books by Bessie Display Name')
        self.assertEqual(vendor1.company_name, 'Books by Bessie Company')
        self.assertEqual(vendor1.email, 'books_sadfvcdt54@intuit.com')
        self.assertEqual(vendor1.phone, '+16505557745')

        billing = vendor1.child_ids.filtered(lambda r: r.type == 'invoice')
        self.assertFalse(bool(billing))

        self.assertEqual(vendor1.city, 'Palo Alto')
        self.assertEqual(vendor1.country_id.name, 'United States')
        self.assertEqual(vendor1.state_id.name, 'California')
        self.assertEqual(vendor1.street, '15 Main St.')
        self.assertFalse(vendor1.street2)
        self.assertEqual(vendor1.zip, '94303')

        shipping = vendor1.child_ids.filtered(lambda r: r.type == 'delivery')
        self.assertEqual(shipping.city, 'Palo Alto Mid')
        self.assertEqual(shipping.country_id.name, 'United States')
        self.assertEqual(shipping.state_id.name, 'California')
        self.assertEqual(shipping.street, '10 Main St.')
        self.assertEqual(shipping.street2, '43 Main St.')
        self.assertEqual(shipping.zip, '94344')

    def test_auto_map_accounts(self):
        mapped_account_ids = self.map_all_accounts().mapped('qbo_id')
        for qbo_id in ['33', '81', '79', '113']:
            self.assertIn(qbo_id, mapped_account_ids)

    @patch(request_client)
    def test_update_map_product_from_odoo_product(self, *args):
        # Unmap default company stock account
        self.qi.write({
            'qi_default_stock_valuation_account_id': False,
        })
        records = self.env['qbo.map.product'].search([
            ('qbo_id', 'in', ['67', '71']),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertTrue(len(records) == 2)
        inventory_67 = records.filtered(lambda r: r.qbo_id == '67')
        inventory_71 = records.filtered(lambda r: r.qbo_id == '71')

        inventory_67.create_instance_in_odoo()
        product1 = inventory_67.product_id
        self.assertTrue(product1.id)

        # Assert raise due to product has no a mapping
        inventory_67.write({'product_id': False})
        with self.assertRaises(ValidationError):
            product1._get_map_instance_or_raise(self.qi.id, PRODUCT)

        # Assert raise due to product has the several mapping
        records.write({'product_id': product1.id})
        with self.assertRaises(ValidationError):
            product1._get_map_instance_or_raise(self.qi.id, PRODUCT)

        inventory_71.write({'product_id': False})
        get_inventory_67 = product1._get_map_instance_or_raise(self.qi.id, PRODUCT)
        self.assertEqual(inventory_67, get_inventory_67)

        # Assert raise due to unmapped accounts
        with self.assertRaises(ValidationError):
            product1._check_qbo_requirements(self.qi.id)

        self.map_sales_income()
        self.map_cost_of_gods_sold()
        self.map_default_company_stock_account()
        self.map_inventory_asset()
        product1._check_qbo_requirements(self.qi.id)

        # Update product after all checks
        with self.patcher(PRODUCT):
            inventory_67.update_qbo_one()

    @patch(request_client)
    def test_update_map_partner_from_odoo_partner(self, *args):
        customer_3 = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '3'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertTrue(len(customer_3) == 1)

        customer_3.create_instance_in_odoo()

        partner1 = customer_3.partner_id
        self.assertTrue(partner1.id)

        # Update the patrner after all checks
        with self.patcher(CUSTOMER):
            customer_3.update_qbo_one()

    def test_check_constraints_export_customer_to_qbo(self):
        partner1 = self.env['res.partner'].create({
            'name': 'John Wayne Customer',
        })
        # 1. No map-partner before export
        qbo_mapping_ids = partner1.qbo_mapping_ids.filtered(
            lambda r: r.quickbooks_integration_id == self.qi
        )
        self.assertFalse(qbo_mapping_ids)

        # 2. Assert raise due to more than one related map-objects exists
        map_partners = self.env['qbo.map.partner'].search([
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=2)

        self.assertTrue(len(map_partners) == 2)
        map_partners.write({'partner_id': partner1.id})

        with self.assertRaises(ValidationError):
            partner1.with_context(with_qbo_partner_type=CUSTOMER).action_export_to_quickbooks()

    @patch(request_client)
    def test_export_customer_to_qbo(self, *args):
        partner = self.env['res.partner'].create({
            'name': 'John Wayne Customer',
        })

        # No map-partner before export
        map_partner = partner._get_qbo_mapping(self.qi.id, CUSTOMER)
        self.assertFalse(map_partner)

        # Perform export
        self.assertFalse(partner.is_qbo_sync_done)

        with self.patcher(CUSTOMER):
            partner.with_context(with_qbo_partner_type=CUSTOMER).action_export_to_quickbooks()

        # Map-partner exist
        map_partner = partner._get_qbo_mapping(self.qi.id, CUSTOMER)

        self.assertTrue(len(map_partner) == 1)
        self.assertTrue(map_partner.qbo_lib_type == CUSTOMER)
        self.assertTrue(partner.is_qbo_sync_done)

    def test_check_constraints_export_vendor_to_qbo(self):
        partner1 = self.env['res.partner'].create({
            'name': 'John Wayne Vendor',
        })

        # 1. No map-partner before export
        qbo_mapping_ids = partner1.qbo_mapping_ids.filtered(
            lambda r: r.quickbooks_integration_id == self.qi
        )
        self.assertFalse(qbo_mapping_ids)

        # 2. Assert raise due to more than one related map-objects exists
        map_partners = self.env['qbo.map.partner'].search([
            ('qbo_lib_type', '=', VENDOR),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=2)

        self.assertTrue(len(map_partners) == 2)
        map_partners.write({'partner_id': partner1.id})

        with self.assertRaises(ValidationError):
            partner1.with_context(with_qbo_partner_type=VENDOR).action_export_to_quickbooks()

    @patch(request_client)
    def test_export_vendor_to_qbo(self, *args):
        partner = self.env['res.partner'].create({
            'name': 'John Wayne Vendor',
        })

        # No map-partner before export
        map_partner = partner.qbo_mapping_ids.filtered(
            lambda r: r.quickbooks_integration_id == self.qi
        )
        self.assertFalse(map_partner)

        # Perform export
        self.assertFalse(partner.is_qbo_sync_done)
        with self.patcher(VENDOR):
            partner.with_context(with_qbo_partner_type=VENDOR).action_export_to_quickbooks()

        # Map-partner exist
        map_partner = partner.qbo_mapping_ids.filtered(
            lambda r: r.quickbooks_integration_id == self.qi
        )
        self.assertTrue(len(map_partner) == 1)
        self.assertTrue(map_partner.qbo_lib_type == VENDOR)
        self.assertTrue(partner.is_qbo_sync_done)

    @patch(request_client)
    def test_export_inventory_product(self, *args):
        self.map_all_accounts()

        product = self.env['product.product'].create({
            'name': 'Inventory product',
            'type': 'consu',
            'is_storable': True,
            'categ_id': self.env.ref('product.product_category_goods').id,
        })
        mapping = product._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertFalse(mapping)
        self.assertFalse(product.is_qbo_sync_done)

        with self.patcher(PRODUCT):
            product.action_export_to_quickbooks()

        mapping = product._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(product.is_qbo_sync_done)

    @patch(request_client)
    def test_check_constraints_export_inventory_product(self, *args):
        # Unmap default company stock account
        self.qi.write({
            'qi_default_stock_valuation_account_id': False,
        })
        product1 = self.env['product.product'].create({
            'name': 'Inventory product',
            'type': 'consu',
            'is_storable': True,
            'categ_id': self.env.ref('product.product_category_goods').id,
        })

        # 1. No map-product before export
        mapping = product1._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertFalse(mapping)
        self.assertFalse(product1.is_qbo_sync_done)

        # 2. Assert raise due to more than one related mapping exists
        map_products = self.env['qbo.map.product'].search([
            ('qbo_lib_type', '=', PRODUCT),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=2)
        self.assertTrue(len(map_products) == 2)
        map_products.write({'product_id': product1.id})

        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 3. Assert raise due to unmapped accounts
        map_products.write({
            'qbo_name': 'Just erase names',
            'product_id': False,
        })
        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 4. Map only income account
        self.map_sales_income()
        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 5. Map income + expense accounts
        self.map_sales_income()
        self.map_cost_of_gods_sold()
        self.map_default_company_stock_account()
        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 6. Map income + expense + inventory accounts
        self.map_sales_income()
        self.map_cost_of_gods_sold()
        self.map_inventory_asset()

        with self.patcher(PRODUCT):
            product1.action_export_to_quickbooks()

        mapping = product1._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(product1.is_qbo_sync_done)

    @patch(request_client)
    def test_export_service_product(self, *args):
        self.map_all_accounts()

        product = self.env['product.product'].create({
            'name': 'Service product',
            'type': 'service',
            'categ_id': self.env.ref('product.product_category_services').id,
        })
        mapping = product._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertFalse(mapping)
        self.assertFalse(product.is_qbo_sync_done)

        with self.patcher(PRODUCT):
            product.action_export_to_quickbooks()

        mapping = product._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(product.is_qbo_sync_done)

    @patch(request_client)
    def test_check_constraints_export_service_product(self, *args):
        product1 = self.env['product.product'].create({
            'name': 'Service product',
            'type': 'service',
            'categ_id': self.env.ref('product.product_category_services').id,
        })
        self.assertFalse(product1.is_qbo_sync_done)

        # 1. No map-product before export
        mapping = product1._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertFalse(mapping)

        # 2. Assert raise due to more than one related mapping exists
        map_products = self.env['qbo.map.product'].search([
            ('qbo_lib_type', '=', PRODUCT),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=2)
        self.assertTrue(len(map_products) == 2)
        map_products.write({'product_id': product1.id})

        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 3. Assert raise due to unmapped accounts
        map_products.write({
            'qbo_name': 'Just erase names',
            'product_id': False,
        })
        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 4. Map only income account
        self.map_sales_income()
        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 5. Map income + expense accounts
        self.map_sales_income()
        self.map_cost_of_gods_sold()

        with self.patcher(PRODUCT):
            product1.action_export_to_quickbooks()

        mapping = product1._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(product1.is_qbo_sync_done)

    @patch(request_client)
    def test_export_consu_product(self, *args):
        self.map_all_accounts()

        product = self.env['product.product'].create({
            'name': 'Consumable product',
            'type': 'consu',
            'categ_id': self.env.ref('product.product_category_goods').id,
        })
        mapping = product._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertFalse(mapping)
        self.assertFalse(product.is_qbo_sync_done)

        with self.patcher(PRODUCT):
            product.action_export_to_quickbooks()

        mapping = product._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(product.is_qbo_sync_done)

    @patch(request_client)
    def test_check_constraints_export_consu_product(self, *args):
        product1 = self.env['product.product'].create({
            'name': 'Consumable product',
            'type': 'consu',
            'categ_id': self.env.ref('product.product_category_goods').id,
        })
        self.assertFalse(product1.is_qbo_sync_done)

        # 1. No map-product before export
        mapping = product1._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertFalse(mapping)

        # 2. Assert raise due to more than one related mapping exists
        map_products = self.env['qbo.map.product'].search([
            ('qbo_lib_type', '=', PRODUCT),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=2)
        self.assertTrue(len(map_products) == 2)
        map_products.write({'product_id': product1.id})

        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 3. Assert raise due to unmapped accounts
        map_products.write({
            'qbo_name': 'Just erase names',
            'product_id': False,
        })
        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 4. Map only income account
        self.map_sales_income()
        with self.assertRaises(ValidationError):
            product1.action_export_to_quickbooks()

        # 5. Map income + expense accounts
        self.map_sales_income()
        self.map_cost_of_gods_sold()

        with self.patcher(PRODUCT):
            product1.action_export_to_quickbooks()

        mapping = product1._get_qbo_mapping(self.qi.id, PRODUCT)
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(product1.is_qbo_sync_done)

    @patch(request_client)
    def test_export_customer_invoice(self, *args):
        self.map_all_accounts()

        map_product = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '1'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_customer = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '2'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        map_product.create_instance_in_odoo()
        map_customer.create_instance_in_odoo()

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': map_customer.partner_id.id,
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'price_unit': 10.0,
                'quantity': 1,
                'product_id': map_product.product_id.id,
            })],
        })

        # Confirm invoice
        invoice.action_post()
        # Map-invoice before export
        mapping = invoice._get_qbo_mapping()
        self.assertFalse(mapping)
        self.assertFalse(invoice.is_qbo_sync_done)

        with self.patcher(INVOICE):
            invoice.action_export_to_quickbooks()

        # Map-invoice after export
        mapping = invoice._get_qbo_mapping()
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(invoice.is_qbo_sync_done)

    @patch(request_client)
    def test_constraints_export_customer_invoice(self, *args):
        customer = self.env['res.partner'].create({
            'name': 'Test Invoice Customer',
        })
        product = self.env['product.product'].create({
            'name': 'Test Invoice Product',
        })
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
        })
        self.assertFalse(invoice.is_qbo_sync_done)

        # 2.
        try:
            invoice.action_export_to_quickbooks()
        except ValidationError as ex:
            self.assertIn('You need to assign partner', ex.args[0])

        # 3.
        invoice.write({
            'partner_id': customer.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'price_unit': 10.0,
                'quantity': 1,
                'product_id': product.id,
                'account_id': self.env.ref('quickbooks_sync_online.a_expense').id,
            })],
        })

        map_customer = self.env['qbo.map.partner'].search([
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=1)
        self.assertTrue(map_customer)
        map_customer.write({'partner_id': customer.id})

        map_product = self.env['qbo.map.product'].search([
            ('qbo_lib_type', '=', PRODUCT),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=1)
        self.assertTrue(map_product)
        map_product.write({'product_id': product.id})

        # 4.
        try:
            invoice.action_export_to_quickbooks()
        except ValidationError as ex:
            self.assertIn('Confirm invoice', ex.args[0])

        invoice.action_post()

        # 5.
        with self.patcher(INVOICE):
            invoice.action_export_to_quickbooks()
        self.assertTrue(invoice.is_qbo_sync_done)

        # Map-invoice after export
        mapping = invoice._get_qbo_mapping()
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(invoice.is_qbo_sync_done)

    @patch(request_client)
    def test_export_vendor_bill(self, *args):
        self.map_all_accounts()

        map_product = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '67'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_vendor = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '31'),
            ('qbo_lib_type', '=', VENDOR),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        map_product.create_instance_in_odoo()
        map_vendor.create_instance_in_odoo()

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'invoice_date': date.today(),
            'partner_id': map_vendor.partner_id.id,
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.expenses_journal').id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'price_unit': 10.0,
                'quantity': 1,
                'product_id': map_product.product_id.id,
            })],
        })

        # Confirm invoice
        bill.action_post()
        # Map-invoice before export
        mapping = bill._get_qbo_mapping()
        self.assertFalse(mapping)
        self.assertFalse(bill.is_qbo_sync_done)

        with self.patcher(BILL):
            bill.action_export_to_quickbooks()

        # Map-invoice after export
        mapping = bill._get_qbo_mapping()
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(bill.is_qbo_sync_done)

    @patch(request_client)
    def test_constraints_export_vendor_bill(self, *args):
        vendor = self.env['res.partner'].create({
            'name': 'Test Bill Vendor',
        })
        product = self.env['product.product'].create({
            'name': 'Test Bill Product',
        })
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'invoice_date': date.today(),
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.expenses_journal').id,
        })
        self.assertFalse(bill.is_qbo_sync_done)

        # 2.
        try:
            bill.action_export_to_quickbooks()
        except ValidationError as ex:
            self.assertIn('You need to assign partner', ex.args[0])

        # 3.
        map_vendor = self.env['qbo.map.partner'].search([
            ('qbo_lib_type', '=', VENDOR),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=1)
        self.assertTrue(map_vendor)
        map_vendor.write({'partner_id': vendor.id})

        bill.write({'partner_id': vendor.id})

        # 4.
        try:
            bill.action_export_to_quickbooks()
        except ValidationError as ex:
            self.assertIn('You need add products', ex.args[0])

        # 5.
        map_product = self.env['qbo.map.product'].search([
            ('qbo_lib_type', '=', PRODUCT),
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=1)
        self.assertTrue(map_product)
        map_product.write({'product_id': product.id})

        bill.write({
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'price_unit': 10.0,
                'quantity': 1,
                'product_id': product.id,
                'account_id': self.env.ref('quickbooks_sync_online.a_expense').id,
            })],
        })

        # 6.
        try:
            bill.action_export_to_quickbooks()
        except ValidationError as ex:
            self.assertIn('Confirm invoice', ex.args[0])

        bill.action_post()

        # 7.
        try:
            bill.action_export_to_quickbooks()
        except ValidationError as ex:
            self.assertIn('Accounts Payable', ex.args[0])

        self.map_account_payable()

        # 8.
        with self.patcher(BILL):
            bill.action_export_to_quickbooks()

        # Map-invoice after export
        mapping = bill._get_qbo_mapping()
        self.assertTrue(len(mapping) == 1)
        self.assertTrue(bill.is_qbo_sync_done)

    @patch(request_client)
    def test_pay_customer_invoice(self, *args):
        self.map_all_accounts()

        map_product = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '1'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_customer = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '2'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        map_product.create_instance_in_odoo()
        map_customer.create_instance_in_odoo()

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': map_customer.partner_id.id,
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'price_unit': 1000.0,
                'quantity': 1,
                'product_id': map_product.product_id.id,
            })],
        })

        invoice.action_post()

        with self.patcher(INVOICE):
            invoice.action_export_to_quickbooks()

        map_invoice = invoice._get_qbo_mapping()
        self.assertTrue(len(map_invoice) == 1)

        payments = self.env['qbo.map.payment'].search([
            ('txn_id', '=', map_invoice.id),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        self.assertFalse(payments)

        # 2. Make a partially payment amount by cash ('1')
        pay_id = self.patcher.make_intuit_payment(map_invoice.qbo_id, 'Invoice', 900.0, '1')

        def _get_outstanding_account_patch(payment, *args, **kw):
            return payment.env.ref('quickbooks_sync_online.o_payments')

        self.patch(type(self.env['account.payment']), '_get_outstanding_account', _get_outstanding_account_patch)

        with self.patcher(PAYMENT):
            payment = self.env['qbo.map.payment'].fetch_qbo_one_by_pk(pay_id, 'Payment', self.qi.id)

            pay = self.env['qbo.map.payment'] \
                .with_context(
                    default_txn_id=map_invoice.id,
                    default_txn_amount='900.0',
                ).create_qbo_mapping_from_response(payment, self.qi.id, odoo_id=None)

        self.assertTrue(len(pay) == 1)
        self.assertEqual(pay.pay_method, '1')
        self.assertEqual(pay.payment_id.id, False)
        self.assertEqual(pay.txn_type, 'invoice')
        self.assertEqual(pay.currency_ref, 'USD')
        self.assertEqual(pay.txn_amount, '900.0')
        self.assertEqual(pay.invoice_id, invoice)
        self.assertEqual(pay.txn_date, datetime.today().strftime('%Y-%m-%d'))

        pay._try_to_map_payment()
        self.assertFalse(pay.payment_id)

        # 3. Register payment
        try:
            pay.register_payment_in_odoo(reconcile=False)
        except ValidationError as ex:
            self.assertIn('It is not possible to register payment in Odoo', ex.args[0])

        self.map_payment_defaults()
        pay.register_payment_in_odoo(reconcile=False)

        payment = pay.payment_id
        payment.ensure_one()

        self.assertEqual(payment.memo, invoice.name)
        self.assertEqual(int(payment.amount), 900)
        self.assertTrue(payment.state in ['in_process', 'paid'])
        self.assertTrue(invoice.payment_state in ['partial', 'in_payment'])

    @patch(request_client)
    def test_pay_creditnote(self, *args):
        self.qi.write({
            'allow_out_invoice_export': True,
        })

        self.map_all_accounts()

        map_product = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '1'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_customer = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '2'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        map_product.create_instance_in_odoo()
        map_customer.create_instance_in_odoo()

        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': map_customer.partner_id.id,
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'price_unit': 1000.0,
                'quantity': 1,
                'product_id': map_product.product_id.id,
            })],
        })

        credit_note.action_post()

        with self.patcher(CREDIT_NOTE):
            credit_note.action_export_to_quickbooks()

        mapping = credit_note._get_qbo_mapping()
        self.assertTrue(len(mapping) == 1)

        def _get_outstanding_account_patch(payment, *args, **kw):
            return payment.env.ref('quickbooks_sync_online.o_payments')

        self.patch(type(self.env['account.payment']), '_get_outstanding_account', _get_outstanding_account_patch)

        wizard = self.env['account.payment.register'] \
            .with_context(
                active_model=credit_note._name,
                active_ids=credit_note.ids,
            ).create({
                'journal_id': self.env.ref('quickbooks_sync_online.bank_journal').id,
            })

        payment = wizard._create_payments()
        payment.ensure_one()

        self.assertEqual(int(payment.amount), 1000)
        self.assertTrue(payment.state in ['in_process', 'paid'])

        self.assertFalse(payment.is_qbo_export_allowed)

    @patch(request_client)
    def test_pay_customer_invoice_in_odoo(self, *args):
        self.map_all_accounts()
        self.map_payment_defaults()

        map_product = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '1'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_customer = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '2'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        map_product.create_instance_in_odoo()
        map_customer.create_instance_in_odoo()

        # A.
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': map_customer.partner_id.id,
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'price_unit': 1000.0,
                'quantity': 1,
                'product_id': map_product.product_id.id,
            })],
        })

        invoice.action_post()

        with self.patcher(INVOICE):
            invoice.action_export_to_quickbooks()

        map_invoice = invoice.qbo_mapping_ids
        self.assertTrue(len(map_invoice) == 1)

        ctx = {
            'active_model': 'account.move',
            'active_ids': invoice.ids,
        }
        ac_pay_reg1 = self.env['account.payment.register'].with_context(**ctx).create({
            'amount': 400.0,
            'journal_id': self.env.ref('quickbooks_sync_online.bank_journal').id,
            'partner_type': 'customer',
            'payment_date': date.today(),
            'payment_method_line_id':
                self.env.ref('quickbooks_sync_online.line_check_in').id,
            'currency_id': invoice.currency_id.id,
            'payment_type': 'inbound',
        })
        payment_1 = ac_pay_reg1._create_payments()

        ac_pay_reg2 = self.env['account.payment.register'].with_context(**ctx).create({
            'amount': invoice.amount_total - 400.0,
            'journal_id': self.env.ref('quickbooks_sync_online.bank_journal').id,
            'partner_type': 'customer',
            'payment_date': date.today(),
            'payment_method_line_id':
                self.env.ref('quickbooks_sync_online.line_check_in').id,
            'currency_id': invoice.currency_id.id,
            'payment_type': 'inbound',
        })
        payment_2 = ac_pay_reg2._create_payments()

        payments = payment_1 + payment_2

        self.assertTrue(len(payment_1.qbo_mapping_ids) == 0)
        self.assertTrue(len(payment_2.qbo_mapping_ids) == 0)

        # Map `payment.joutnal_id` to any `qbo.map.payment.method` before export.
        map_pay_met = self.env['qbo.map.payment.method'].search([
            ('quickbooks_integration_id', '=', self.qi.id),
        ], limit=1)
        journal = payments.mapped('journal_id')

        self.assertTrue(len(journal) == 1)

        map_pay_met.journal_id = journal.id

        with self.patcher(PAYMENT):
            payments.with_context(qbo_invoice_export_allowed=True).action_export_to_quickbooks()

        self.assertTrue(len(payment_1.qbo_mapping_ids) == 1)
        self.assertTrue(payment_1.is_qbo_sync_done)
        self.assertTrue(payment_1.is_excluded_from_qbo_sync)

        self.assertTrue(len(payment_2.qbo_mapping_ids) == 1)
        self.assertTrue(payment_2.is_qbo_sync_done)
        self.assertTrue(payment_2.is_excluded_from_qbo_sync)

        self.assertTrue(map_invoice.payment_state in ['paid', 'in_payment'])
        self.assertTrue(len(map_invoice.payment_ids) == 2)

    @patch(request_client)
    def test_pay_customer_credit_in_odoo(self, *args):
        self.map_all_accounts()
        self.map_payment_defaults()

        map_product = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '1'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_customer = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '2'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        map_product.create_instance_in_odoo()
        map_customer.create_instance_in_odoo()

        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': map_customer.partner_id.id,
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'price_unit': 1000.0,
                'quantity': 1,
                'product_id': map_product.product_id.id,
            })],
        })
        credit_note.action_post()

        with self.patcher(CREDIT_NOTE):
            credit_note.action_export_to_quickbooks()

        map_credit_note = credit_note._get_qbo_mapping()
        self.assertTrue(len(map_credit_note) == 1)

        ctx = {
            'active_model': 'account.move',
            'active_ids': credit_note.ids,
        }
        ac_pay_reg1 = self.env['account.payment.register'].with_context(**ctx).create({
            'amount': 400.0,
            'journal_id': self.env.ref('quickbooks_sync_online.bank_journal').id,
            'partner_type': 'customer',
            'payment_date': date.today(),
            'payment_method_line_id':
                self.env.ref('quickbooks_sync_online.line_check_in').id,
            'currency_id': credit_note.currency_id.id,
            'payment_type': 'inbound',
        })
        payment_1 = ac_pay_reg1._create_payments()

        ac_pay_reg2 = self.env['account.payment.register'].with_context(**ctx).create({
            'amount': credit_note.amount_total - 400.0,
            'journal_id': self.env.ref('quickbooks_sync_online.bank_journal').id,
            'partner_type': 'customer',
            'payment_date': date.today(),
            'payment_method_line_id':
                self.env.ref('quickbooks_sync_online.line_check_in').id,
            'currency_id': credit_note.currency_id.id,
            'payment_type': 'inbound',
        })
        payment_2 = ac_pay_reg2._create_payments()

        payments = payment_1 + payment_2
        company_payment_ids = self.qi._search_to_qbo_payments()

        for p in payments:
            self.assertTrue(p.id not in company_payment_ids.ids)

    @patch(request_client)
    def test_requires_update_partner_to_qbo(self, *args):
        # A. Create and export new partner
        ctx = {
            'with_qbo_partner_type': VENDOR,
        }

        country_id = self.env.ref('base.us', False) and self.env.ref('base.us').id
        state_id = self.env.ref('base.state_us_1', False) and self.env.ref('base.state_us_1').id

        parent_partner = self.env['res.partner'].create({
            'name': 'John Wayne Vendor Parent',
        })
        partner = self.env['res.partner'].create({
            'name': 'John Wayne Vendor',
            'parent_id': parent_partner.id,
            'email': 'mail@mail.info',
            'phone': '8029-555555',
            'country_id': country_id,
            'city': 'Minsk',
            'state_id': state_id,
            'street': 'Lenina',
            'street2': 'Stalina',
            'zip': '666',
        })

        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'name': 'John Wayne Vendor-2'})
        self.assertFalse(partner.is_qbo_update_required)

        # Perform export
        with self.patcher(VENDOR):
            partner.with_context(**ctx).action_export_to_quickbooks()

        # Map-partner exist
        map_partner = partner.qbo_mapping_ids.filtered(
            lambda r: r.quickbooks_integration_id == self.qi
        )
        self.assertTrue(len(map_partner) == 1)
        self.assertTrue(map_partner.qbo_lib_type == VENDOR)
        self.assertTrue(partner.is_qbo_sync_done)

        # B. Change 'track-fields' in partner after export

        self.assertFalse(partner.is_qbo_update_required)
        partner.with_context(no_mark_quickbooks_update=True).write({
            'name': 'John Wayne Vendor-3',
        })
        self.assertFalse(partner.is_qbo_update_required)

        # 1. name
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'name': 'John Wayne Vendor-4'})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 2. parent_id
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'parent_id': False})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 3. phone
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'phone': '8044-555555'})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 5. state_id
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'state_id': False})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 6. country_id
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'country_id': False})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 7. city
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'city': 'Kiev'})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 8. street
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'street': 'Peremen'})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 9. street2
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'street2': 'Pr. Peremen'})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 10. zip
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'zip': '999'})
        self.assertTrue(partner.is_qbo_update_required)
        partner.write({'is_qbo_update_required': False})

        # 11. email
        self.assertFalse(partner.is_qbo_update_required)
        partner.write({'email': 'mail@mail.com'})
        self.assertTrue(partner.is_qbo_update_required)

        records_to_update = self.env['res.partner'].search([('is_qbo_update_required', '=', True)])
        self.assertIn(partner.id, records_to_update.ids)

        # Perform update
        with self.patcher(VENDOR):
            partner.with_context(**ctx).action_export_to_quickbooks()

        self.assertFalse(partner.is_qbo_update_required)

        # 11. change non-track field --> website
        partner.write({'website': 'https://portal.pl'})
        self.assertFalse(partner.is_qbo_update_required)

        records_to_update = self.env['res.partner'].search([('is_qbo_update_required', '=', True)])
        self.assertNotIn(partner.id, records_to_update.ids)

    @patch(request_client)
    def test_get_taxes_from_qbo_taxable_customer(self, *args):
        self.map_all_accounts()
        tax = self.create_tax()

        MAP_PARTNER = self.env['qbo.map.partner']

        def refresh_qbo_mapping_body(*args, **kw):
            return

        # Patch 'refresh_qbo_mapping_body()' method for 'qbo.map.partner'
        self.patch(type(MAP_PARTNER), 'refresh_qbo_mapping_body', refresh_qbo_mapping_body)

        map_product_1 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '4'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_product_2 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '1'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_customer = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '3'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        product_1 = map_product_1.create_instance_in_odoo()
        product_2 = map_product_2.create_instance_in_odoo()
        customer = map_customer.create_instance_in_odoo()

        product_1.write({
            'taxes_id': [(6, 0, tax.ids)],
        })

        sale_order = self.env['sale.order'].create({
            'partner_id': customer.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'name': map_product_1.qbo_name,
                    'product_id': product_1.id,
                    'product_uom_qty': 2,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'price_unit': 42,
                }),
                (0, 0, {
                    'name': map_product_2.qbo_name,
                    'product_id': product_2.id,
                    'product_uom_qty': 1,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'price_unit': 58,
                }),
            ],
        })

        taxes_before = self.env['account.tax'].search([
            ('company_id', '=', self.company.id)
        ])
        self.assertTrue(len(taxes_before) == 1)

        with self.patcher(SALE_ORDER):
            sale_order.get_qbo_taxes_from_salereceipt()

        taxes_after = self.env['account.tax'].search([
            ('company_id', '=', self.company.id)
        ])
        self.assertTrue(len(taxes_after) == 5)

        self.assertTrue(sale_order.is_qbo_sync_done)

        salereceipt = sale_order._get_map_instance_or_raise(self.qi.id, SALE_ORDER)

        self.assertTrue(str(salereceipt.total_tax), '7.77')
        self.assertTrue(len(salereceipt.qbo_tax_ids) == 4)

        line_1 = sale_order.order_line.filtered(lambda r: r.product_id == product_1)
        line_2 = sale_order.order_line.filtered(lambda r: r.product_id == product_2)
        self.assertEqual(
            sorted(line_1.tax_ids.ids),
            sorted(salereceipt.qbo_tax_ids.mapped('tax_id.id')),
        )
        self.assertEqual(
            sorted(line_2.tax_ids.ids),
            [],  # Because of TaxCodeRef --> NON in received json
        )
        self.assertAlmostEqual(sale_order.amount_total, 149.77, 2)

    @patch(request_client)
    def test_get_taxes_from_qbo_non_taxable_customer(self, *args):
        self.map_all_accounts()
        tax = self.create_tax()

        MAP_PARTNER = self.env['qbo.map.partner']

        def refresh_qbo_mapping_body(*args, **kw):
            return

        # Patch 'refresh_qbo_mapping_body()' method for 'qbo.map.partner'
        self.patch(type(MAP_PARTNER), 'refresh_qbo_mapping_body', refresh_qbo_mapping_body)

        map_product_1 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '4'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_product_2 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '1'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_customer = self.env['qbo.map.partner'].search([
            ('qbo_id', '=', '4'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        product_1 = map_product_1.create_instance_in_odoo()
        product_2 = map_product_2.create_instance_in_odoo()
        customer = map_customer.create_instance_in_odoo()

        sale_order = self.env['sale.order'].create({
            'partner_id': customer.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'name': map_product_1.qbo_name,
                    'product_id': product_1.id,
                    'product_uom_qty': 2,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'price_unit': 42,
                    'tax_ids': [(6, 0, tax.ids)],
                }),
                (0, 0, {
                    'name': map_product_2.qbo_name,
                    'product_id': product_2.id,
                    'product_uom_qty': 1,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'price_unit': 58,
                    'tax_ids': False,
                }),
            ],
        })

        taxes_before = self.env['account.tax'].search([
            ('company_id', '=', self.company.id)
        ])
        self.assertTrue(len(taxes_before) == 1)

        with self.patcher(SALE_ORDER):
            sale_order.get_qbo_taxes_from_salereceipt()

        taxes_after = self.env['account.tax'].search([
            ('company_id', '=', self.company.id)
        ])
        self.assertTrue(len(taxes_after) == 1)
        self.assertFalse(sale_order.is_qbo_sync_done)

        with self.assertRaises(ValidationError):
            # No mapping due to `non-taxable customer`
            sale_order._get_map_instance_or_raise(self.qi.id, SALE_ORDER)

        line_1 = sale_order.order_line.filtered(lambda r: r.product_id == product_1)
        line_2 = sale_order.order_line.filtered(lambda r: r.product_id == product_2)

        self.assertFalse(bool(line_1.tax_ids))
        self.assertFalse(bool(line_2.tax_ids))

        self.assertEqual(str(sale_order.amount_total), '142.0')

    @patch(request_client)
    def test_constraints_get_taxes_from_qbo(self, *args):
        self.map_all_accounts()
        tax = self.create_tax()

        MAP_PARTNER = self.env['qbo.map.partner']

        def refresh_qbo_mapping_body(*args, **kw):
            return

        # Patch 'refresh_qbo_mapping_body()' method for 'qbo.map.partner'
        self.patch(type(MAP_PARTNER), 'refresh_qbo_mapping_body', refresh_qbo_mapping_body)

        map_product = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '4'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        map_customer = MAP_PARTNER.search([
            ('qbo_id', '=', '3'),
            ('qbo_lib_type', '=', CUSTOMER),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        product = map_product.create_instance_in_odoo()
        customer = map_customer.create_instance_in_odoo()

        # 1. SaleOrder not in 'draft' state
        sale_order_1 = self.env['sale.order'].create({
            'partner_id': customer.id,
            'company_id': self.company.id,
            'order_line': [(0, 0, {
                'name': map_product.qbo_name,
                'product_id': product.id,
                'product_uom_qty': 1,
                'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                'price_unit': 50,
                'tax_ids': [(6, 0, tax.ids)],
            })],
        })
        sale_order_1.action_confirm()

        with self.assertRaises(UserError):
            sale_order_1.get_qbo_taxes_from_salereceipt()

        # 2. No products
        map_customer.write({'partner_id': customer.id})
        map_product.write({'product_id': product.id})
        sale_order_4 = self.env['sale.order'].create({
            'partner_id': customer.id,
            'company_id': self.company.id,
        })

        with self.assertRaises(UserError):
            sale_order_4.get_qbo_taxes_from_salereceipt()

        # 3. Happy-path case
        sale_order_5 = self.env['sale.order'].create({
            'partner_id': customer.id,
            'company_id': self.company.id,
            'order_line': [(0, 0, {
                'name': map_product.qbo_name,
                'product_id': product.id,
                'product_uom_qty': 1,
                'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                'price_unit': 50,
                'tax_ids': [(6, 0, tax.ids)],
            })],
        })

        sale_order_5._check_qbo_requirements()

        with self.patcher(SALE_ORDER):
            sale_order_5.get_qbo_taxes_from_salereceipt()

        self.assertTrue(sale_order_5.is_qbo_sync_done)

    def test_get_products_to_qbo_export_method(self):
        partner = self.env['res.partner'].create({
            'name': 'Test Invoice Partner',
        })
        product1 = self.env['product.product'].create({
            'name': 'Test Invoice Product1',
        })
        product2 = self.env['product.product'].create({
            'name': 'Test Invoice Product2',
        })
        product3 = self.env['product.product'].create({
            'name': 'Test Invoice Product3',
        })
        product4 = self.env['product.product'].create({
            'name': 'Test Invoice Product4',
        })
        invoice1 = self.env['account.move'].create({
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Test line',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': product1.id,
                    'account_id': self.env.ref('quickbooks_sync_online.a_expense').id,
                }),
            ],
        })
        invoice2 = self.env['account.move'].create({
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Test line',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': product2.id,
                    'account_id': self.env.ref('quickbooks_sync_online.a_expense').id,
                }),
            ],
        })

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'invoice_date': date.today(),
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.expenses_journal').id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Test line1',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': product3.id,
                    'account_id': self.env.ref('quickbooks_sync_online.a_expense').id,
                }),
                (0, 0, {
                    'name': 'Test line2',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': product4.id,
                    'account_id': self.env.ref('quickbooks_sync_online.a_expense').id,
                }),
            ],
        })

        all_invoices = invoice1 + invoice2 + bill

        # 1.
        self.qi.write({
            'include_product_to_invoice': True,
            'sync_product_as_category': False,
        })

        products = self.env['product.product']
        for invoice in all_invoices:
            products |= invoice._get_products_to_qbo_export()

        self.assertIn(product1.id, products.ids)
        self.assertIn(product2.id, products.ids)
        self.assertIn(product3.id, products.ids)
        self.assertIn(product4.id, products.ids)

        # 2.
        self.qi.write({
            'include_product_to_invoice': False,
            'sync_product_as_category': False,
        })

        products = self.env['product.product']
        for invoice in all_invoices:
            products |= invoice._get_products_to_qbo_export()

        self.assertNotIn(product1.id, products.ids)
        self.assertNotIn(product2.id, products.ids)
        self.assertIn(product3.id, products.ids)
        self.assertIn(product4.id, products.ids)

        # 3.
        products = self.env['product.product']
        for invoice in (invoice1 + invoice2):
            products |= invoice._get_products_to_qbo_export()

        self.assertFalse(bool(products))
        self.assertEqual(products._name, 'product.product')

        # 4.
        products = bill._get_products_to_qbo_export()

        self.assertIn(product3.id, products.ids)
        self.assertIn(product4.id, products.ids)

        # 5.
        products = self.env['product.product']
        for invoice in (invoice1 + invoice2):
            products |= invoice._get_products_to_qbo_export()

        self.assertFalse(bool(products))
        self.assertEqual(products._name, 'product.product')

        # 6.
        self.qi.write({
            'sync_product_as_category': True,
        })

        products = self.env['product.category']
        for invoice in all_invoices:
            products |= invoice._get_products_to_qbo_export()

        self.assertEqual(products._name, 'product.category')
        self.assertEqual(products, all_invoices.mapped('invoice_line_ids.product_id.categ_id'))

    def test_create_qbo_invoice_line_method(self):
        partner = self.env['res.partner'].create({
            'name': 'Test Invoice Partner',
        })
        consum_127 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '127'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        consum_127._create_odoo_record()
        product = consum_127.product_id

        consum_137 = self.env['qbo.map.product'].search([
            ('qbo_id', '=', '137'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])
        consum_137.write({
            'category_id': product.categ_id.id,
        })

        invoice = self.env['account.move'].create({
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Test line1',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': product.id,
                    'account_id': self.env.ref('quickbooks_sync_online.a_sale').id
                }),
                (0, 0, {
                    'name': 'Test line2',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': False,
                    'account_id': self.env.ref('quickbooks_sync_online.a_sale').id
                }),
            ],
        })
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'invoice_date': date.today(),
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.expenses_journal').id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Test line1',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': product.id,
                    'account_id': self.env.ref('quickbooks_sync_online.o_expense').id
                }),
                (0, 0, {
                    'name': 'Test line2',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': False,
                    'account_id': self.env.ref('quickbooks_sync_online.o_expense').id
                }),
            ],
        })

        inv_line1 = invoice.invoice_line_ids.filtered(lambda r: r.name == 'Test line1')
        inv_line2 = invoice.invoice_line_ids.filtered(lambda r: r.name == 'Test line2')

        bill_line1 = bill.invoice_line_ids.filtered(lambda r: r.name == 'Test line1')
        bill_line2 = bill.invoice_line_ids.filtered(lambda r: r.name == 'Test line2')

        # 1.
        self.qi.write({
            'include_product_to_invoice': True,
            'sync_product_as_category': False,
        })
        exp_inv_line1 = inv_line1._create_qbo_invoice_line()
        exp_inv_line2 = inv_line2._create_qbo_invoice_line()

        self.assertEqual(
            exp_inv_line1['SalesItemLineDetail']['ItemRef']['value'],
            consum_127.qbo_id,
        )
        self.assertEqual(
            exp_inv_line2['SalesItemLineDetail'].get('ItemRef', {}).get('value', '100500'),
            '100500',
        )

        exp_bill_line1 = bill_line1._create_qbo_invoice_line()
        exp_bill_line2 = bill_line2._create_qbo_invoice_line()

        self.assertEqual(
            exp_bill_line1['ItemBasedExpenseLineDetail']['ItemRef']['value'],
            consum_127.qbo_id,
        )
        self.assertEqual(
            exp_bill_line2['ItemBasedExpenseLineDetail'].get('ItemRef', {}).get('value', 'NONE'),
            'NONE',
        )

        # 2.
        self.qi.write({
            'include_product_to_invoice': True,
            'sync_product_as_category': True,
        })
        exp_inv_line1 = inv_line1._create_qbo_invoice_line()
        exp_inv_line2 = inv_line2._create_qbo_invoice_line()

        self.assertEqual(
            exp_inv_line1['SalesItemLineDetail']['ItemRef']['value'],
            consum_137.qbo_id,
        )
        self.assertEqual(
            exp_inv_line2['SalesItemLineDetail'].get('ItemRef', 'NONE'),
            'NONE',
        )

        exp_bill_line1 = bill_line1._create_qbo_invoice_line()
        exp_bill_line2 = bill_line2._create_qbo_invoice_line()

        self.assertEqual(
            exp_bill_line1['ItemBasedExpenseLineDetail']['ItemRef']['value'],
            consum_137.qbo_id,
        )
        self.assertEqual(
            exp_bill_line2['ItemBasedExpenseLineDetail'].get('ItemRef', 'NONE'),
            'NONE',
        )

        # 3.
        self.qi.write({
            'include_product_to_invoice': False,
            'sync_product_as_category': False,
        })
        exp_inv_line1 = inv_line1._create_qbo_invoice_line()
        exp_inv_line2 = inv_line2._create_qbo_invoice_line()

        self.assertEqual(
            exp_inv_line1['SalesItemLineDetail'].get('ItemRef', 'NONE'),
            'NONE',
        )
        self.assertEqual(
            exp_inv_line2['SalesItemLineDetail'].get('ItemRef', 'NONE'),
            'NONE',
        )

        exp_bill_line1 = bill_line1._create_qbo_invoice_line()
        exp_bill_line2 = bill_line2._create_qbo_invoice_line()

        self.assertEqual(
            exp_bill_line1['ItemBasedExpenseLineDetail']['ItemRef']['value'],
            consum_127.qbo_id,
        )
        self.assertEqual(
            exp_bill_line2['ItemBasedExpenseLineDetail'].get('ItemRef', 'NONE'),
            'NONE',
        )

    def test_get_tax_from_invoice_line(self):
        self.map_all_accounts()
        tax = self.create_tax()

        partner = self.env['res.partner'].create({
            'name': 'Test Invoice Partner',
        })
        product1 = self.env['product.product'].create({
            'name': 'Test Invoice Product1',
            'taxes_id': [(6, 0, tax.ids)],
        })
        product2 = self.env['product.product'].create({
            'name': 'Test Invoice Product2',
            'taxes_id': [(6, 0, tax.ids)],
        })
        product3 = self.env['product.product'].create({
            'name': 'Test Invoice Product3',
        })
        product3.taxes_id = False

        product4 = self.env['product.product'].create({
            'name': 'Test Invoice Product4',
        })
        product4.taxes_id = False

        invoice = self.env['account.move'].create({
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_user_id': self.user.id,
            'company_id': self.company.id,
            'journal_id': self.env.ref('quickbooks_sync_online.sales_journal').id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Test line 1',
                    'price_unit': 10.0,
                    'quantity': 1,
                    'product_id': product1.id,
                    'tax_ids': [(6, 0, tax.ids)],
                    'account_id': self.env.ref('quickbooks_sync_online.a_sale').id
                }),
                (0, 0, {
                    'name': 'Test line 2',
                    'price_unit': 11.0,
                    'quantity': 1,
                    'product_id': product2.id,
                    'tax_ids': False,
                    'account_id': self.env.ref('quickbooks_sync_online.a_sale').id
                }),
                (0, 0, {
                    'name': 'Test line 3',
                    'price_unit': 12.0,
                    'quantity': 1,
                    'product_id': product3.id,
                    'tax_ids': False,
                    'account_id': self.env.ref('quickbooks_sync_online.a_sale').id
                }),
                (0, 0, {
                    'name': 'Test line 4',
                    'price_unit': 12.0,
                    'quantity': 1,
                    'product_id': product4.id,
                    'tax_ids': [(6, 0, tax.ids)],
                    'account_id': self.env.ref('quickbooks_sync_online.a_sale').id
                }),
            ],
        })

        line1, line2, line3, line4 = invoice.invoice_line_ids
        taxcode_line_detail = 'SalesItemLineDetail'

        # 1. Line tax + product tax
        self.assertEqual(line1.name, 'Test line 1')
        export_line1 = line1._create_qbo_invoice_line()
        value = export_line1[taxcode_line_detail]['TaxCodeRef']['value']
        self.assertEqual(value, TAXABLE)

        # 2. Not line tax + product tax
        self.assertEqual(line2.name, 'Test line 2')
        export_line2 = line2._create_qbo_invoice_line()
        value = export_line2[taxcode_line_detail]['TaxCodeRef']['value']
        self.assertEqual(value, TAXABLE)

        # 3. Not line tax + not product tax
        self.assertEqual(line3.name, 'Test line 3')
        export_line3 = line3._create_qbo_invoice_line()
        value = export_line3[taxcode_line_detail]['TaxCodeRef']['value']
        self.assertEqual(value, NON_TAXABLE)

        # 4. Line tax + not product tax
        self.assertEqual(line4.name, 'Test line 4')
        export_line4 = line4._create_qbo_invoice_line()
        value = export_line4[taxcode_line_detail]['TaxCodeRef']['value']
        self.assertEqual(value, TAXABLE)

    def test_inventory_adjustment_class_works(self):
        mapping = self.env['qbo.map.inventory.adjustment'].init_mapping(self.qi.id)

        # 1. Assert raise due to no map-account exists
        with self.assertRaises(ValidationError):
            mapping.init_inventory()

        map_account = self.env['qbo.map.account'].search([
            ('qbo_name', '=', 'Inventory Shrinkage'),
            ('quickbooks_integration_id', '=', self.qi.id),
        ])

        self.qi.write({
            'qi_adjust_inventory_account_id': map_account.id,
        })

        # 2. Assert inventory adjustment object is set up
        inventory = mapping.init_inventory()

        self.assertFalse(inventory.has_payload)

        self.assertTrue(inventory.qbo_object_name == 'InventoryAdjustment')
        self.assertEqual(inventory.AdjustAccountRef['value'], map_account.qbo_id)

        inventory.add_line('123', 10)
        inventory.add_line('125', 12)

        self.assertTrue(inventory.has_payload)

        self.assertEqual(len(inventory.Line), 2)
        self.assertEqual(inventory.Line[0]['ItemAdjustmentLineDetail']['ItemRef']['value'], '123')
        self.assertEqual(inventory.Line[0]['ItemAdjustmentLineDetail']['QtyDiff'], 10)
        self.assertEqual(inventory.Line[1]['ItemAdjustmentLineDetail']['ItemRef']['value'], '125')
        self.assertEqual(inventory.Line[1]['ItemAdjustmentLineDetail']['QtyDiff'], 12)
