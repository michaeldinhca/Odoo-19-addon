# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).


def migrate(cr, version):

    # 1. Skip any action if the temporary table not exists
    cr.execute("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = 'tmp_qbo_company_settings'
    """)
    if not cr.fetchall():
        return

    # 2. Apply company-scoped QBO settings to quickbooks_integration and cleanup the tmp_qbo_company_settings table.
    cr.execute("""
        INSERT INTO quickbooks_integration (
            name,
            company_id,
            currency_id,
            state,
            qb_client_id,
            qb_client_secret,
            qb_env,
            qb_access_token,
            qb_refresh_token,
            qb_company_id,
            enable_invoices_auto_export,
            enable_payments_sync_in,
            enable_payments_sync_out,
            last_customer_payment_point,
            last_vendor_payment_point,
            auto_export_cut_off_date,
            auto_export_batch_limit,
            qi_default_write_off_account_id,
            include_product_to_invoice,
            sync_product_as_category,
            send_storable_product_as_consumable,
            allow_out_invoice_export,
            allow_out_refund_export,
            allow_in_invoice_export,
            allow_in_refund_export,
            qi_default_journal_id,
            export_invoice_as_tax_included,
            derive_partner_from_invoice_to_payment,
            sync_product_stock,
            qi_adjust_inventory_account_id,
            create_uid,
            write_uid,
            create_date,
            write_date
        )
        SELECT
            t.name,
            t.company_id,
            t.currency_id,
            t.state,
            t.qb_client_id,
            t.qb_client_secret,
            COALESCE(t.qb_env, 'production'),
            t.qb_access_token,
            t.qb_refresh_token,
            t.qb_company_id,
            t.enable_invoices_auto_export,
            t.enable_payments_sync_in,
            t.enable_payments_sync_out,
            t.last_customer_payment_point,
            t.last_vendor_payment_point,
            COALESCE(t.auto_export_cut_off_date, CURRENT_DATE),
            COALESCE(t.auto_export_batch_limit, 10),
            t.qi_default_write_off_account_id,
            COALESCE(t.include_product_to_invoice, TRUE),
            t.sync_product_as_category,
            t.send_storable_product_as_consumable,
            COALESCE(t.allow_out_invoice_export, TRUE),
            COALESCE(t.allow_out_refund_export, TRUE),
            COALESCE(t.allow_in_invoice_export, TRUE),
            COALESCE(t.allow_in_refund_export, TRUE),
            t.qi_default_journal_id,
            t.export_invoice_as_tax_included,
            t.derive_partner_from_invoice_to_payment,
            t.sync_product_stock,
            t.qi_adjust_inventory_account_id,
            1,
            1,
            NOW(),
            NOW()
        FROM tmp_qbo_company_settings t
        WHERE NOT EXISTS (
            SELECT 1
            FROM quickbooks_integration qi
            WHERE qi.company_id = t.company_id
        )
    """)

    # 3. Drop the temporary table
    cr.execute("""
        DROP TABLE tmp_qbo_company_settings
    """)
