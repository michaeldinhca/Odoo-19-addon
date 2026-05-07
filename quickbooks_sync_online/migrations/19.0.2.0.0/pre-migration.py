# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).


def migrate(cr, version):
    # Drop all the views from the quickbooks_sync_online module

    cr.execute("""
        SELECT id FROM ir_ui_view
            WHERE inherit_id IN (
                SELECT res_id
                FROM ir_model_data
                WHERE module = 'quickbooks_sync_online'
                AND model = 'ir.ui.view'
            )
    """)

    inherit_ids = cr.fetchall()

    if inherit_ids:
        inherit_ids_ = [x[0] for x in inherit_ids]
        cr.execute(
            'DELETE FROM ir_ui_view WHERE id IN %(inherit_ids)s',
            {'inherit_ids': tuple(inherit_ids_)},
        )
        cr.execute(
            "DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id IN %(inherit_ids)s",
            {'inherit_ids': tuple(inherit_ids_)},
        )

    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id
            FROM ir_model_data
            WHERE module = 'quickbooks_sync_online'
            AND model = 'ir.ui.view'
        )

    """)

    # Drop all the xml-ids from the quickbooks_sync_online module
    cr.execute("""
        DELETE FROM ir_model_data
            WHERE module = 'quickbooks_sync_online'
            AND model = 'ir.ui.view'
    """)

    # Snapshot old company-scoped QBO settings (previously stored on res_company)
    # into a temporary table, so post-migration can safely apply them to
    # quickbooks_integration even if Odoo later drops/changes columns.

    # 1. Check if the res_company table has the QBO credential fields
    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'res_company'
          AND column_name IN ('qbo_client_id')
    """)
    if not cr.fetchall():
        return

    # 2. Drop the temporary table if it exists
    cr.execute("""
        DROP TABLE IF EXISTS tmp_qbo_company_settings
    """)

    # 3. Create the temporary table
    cr.execute("""
        CREATE TABLE tmp_qbo_company_settings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER,
            currency_id INTEGER,
            name VARCHAR,
            state VARCHAR,
            qb_client_id VARCHAR,
            qb_client_secret VARCHAR,
            qb_env VARCHAR,
            qb_access_token VARCHAR,
            qb_refresh_token VARCHAR,
            qb_company_id VARCHAR,
            enable_invoices_auto_export BOOLEAN,
            enable_payments_sync_in BOOLEAN,
            enable_payments_sync_out BOOLEAN,
            last_customer_payment_point VARCHAR,
            last_vendor_payment_point VARCHAR,
            auto_export_cut_off_date DATE,
            auto_export_batch_limit INTEGER,
            qi_default_write_off_account_id INTEGER,
            include_product_to_invoice BOOLEAN,
            sync_product_as_category BOOLEAN,
            send_storable_product_as_consumable BOOLEAN,
            allow_out_invoice_export BOOLEAN,
            allow_out_refund_export BOOLEAN,
            allow_in_invoice_export BOOLEAN,
            allow_in_refund_export BOOLEAN,
            qi_default_journal_id INTEGER,
            export_invoice_as_tax_included BOOLEAN,
            derive_partner_from_invoice_to_payment BOOLEAN,
            sync_product_stock BOOLEAN,
            qi_adjust_inventory_account_id INTEGER
        )
    """)

    # 4. Insert the data into the temporary table
    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'res_company'
          AND column_name = 'qbo_send_stock'
    """)
    sync_product_stock_expr = 'qbo_send_stock' if cr.fetchone() else 'TRUE'

    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'res_company'
          AND column_name = 'qbo_adjust_inventory_account_id'
    """)
    adjust_inventory_account_expr = 'qbo_adjust_inventory_account_id' if cr.fetchone() else 'NULL'

    cr.execute(f"""
        INSERT INTO tmp_qbo_company_settings (
            company_id,
            currency_id,
            name,
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
            qi_adjust_inventory_account_id
        )
        SELECT
            id,
            currency_id,
            name || ' / Quickbooks Integration',
            'draft',
            qbo_client_id,
            qbo_client_secret,
            qbo_environment,
            qbo_access_token,
            qbo_refresh_token,
            qbo_company_id,
            qbo_auto_export,
            qbo_payment_sync_in,
            qbo_payment_sync_out,
            qbo_cus_pay_point,
            qbo_ven_pay_point,
            qbo_export_date_point,
            qbo_export_limit,
            qbo_default_write_off_account_id,
            qbo_sync_product,
            qbo_sync_product_category,
            qbo_sync_storable_to_consumable,
            qbo_export_out_invoice,
            qbo_export_out_refund,
            qbo_export_in_invoice,
            qbo_export_in_refund,
            qbo_def_journal_id,
            qbo_invoice_tax_included,
            FALSE,
            {sync_product_stock_expr},
            {adjust_inventory_account_expr}
        FROM res_company
        WHERE COALESCE(qbo_client_id, '') != ''
          AND COALESCE(qbo_client_secret, '') != ''
    """)
