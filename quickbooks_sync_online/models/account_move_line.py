# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import models, fields

from ..tools import TAXABLE, NON_TAXABLE


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    is_qbo_sync_done = fields.Boolean(
        related='product_id.is_qbo_sync_done',
    )

    @property
    def qbo_partner_type(self):
        return self.move_id.qbo_partner_type

    @property
    def display_type_product(self):
        return self.display_type == 'product'

    def remove_move_reconcile(self):
        # ToDo: Synchronous work of confirmations and cancellations for payments in Odoo / QuickBooks.
        super(AccountMoveLine, self).remove_move_reconcile()

    def _create_qbo_invoice_line(self):
        self.ensure_one()

        customer_move_type = self.move_id.is_customer_move_type

        if self.tax_ids:
            product_tax = self.tax_ids[:1]
        else:
            tax_field = 'taxes_id' if customer_move_type else 'supplier_taxes_id'
            product_tax = getattr(self.product_id, tax_field)[:1]

        if product_tax and product_tax.price_include:
            price_unit = self.price_subtotal / (self.quantity or 1)
        else:
            price_unit = self.price_unit * (1 - self.discount / 100)

        qi = self.move_id.quickbooks_integration

        if qi.qb_is_us_company:
            taxcode_value = TAXABLE if product_tax else NON_TAXABLE
        else:
            taxcodes = self.tax_ids.find_qbo_taxcodes(qi.id, self.qbo_partner_type)
            taxcode_value = taxcodes[0] if taxcodes else ''

        taxcode_line_detail = 'SalesItemLineDetail' if customer_move_type else 'ItemBasedExpenseLineDetail'

        export_line = {
            'Description': self.name,
            'Amount': self.price_subtotal,
            'DetailType': taxcode_line_detail,
            taxcode_line_detail: {
                'Qty': self.quantity,
                'UnitPrice': price_unit,
                'TaxCodeRef': {
                    'value': taxcode_value,
                },
            },
        }

        if not customer_move_type:
            customer = self.purchase_line_id.sale_line_id.order_id.partner_id

            if customer:
                customer = customer._ensure_qbo_currency(self.move_id)
                qbo_partner = customer._get_qbo_mapping(qi.id, 'customer')

                export_line[taxcode_line_detail]['CustomerRef'] = {
                    'value': qbo_partner.qbo_id,
                }

        if not self.product_id:
            return export_line

        if not qi.include_product_to_invoice and customer_move_type:
            return export_line

        if qi.sync_product_as_category:
            record = self.product_id.categ_id
        else:
            record = self.product_id

        mapping = record._get_qbo_mapping(qi.id, 'item')

        export_line[taxcode_line_detail]['ItemRef'] = {
            'name': mapping.qbo_name,
            'value': mapping.qbo_id,
        }

        return export_line
