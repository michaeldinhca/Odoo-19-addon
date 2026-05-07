# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from psycopg2 import sql

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    # 1. Fill out quickbooks_integration_id field for the all classes inherited from qbo.map.abstract

    query = sql.SQL("""
        UPDATE {table} tbl
        SET quickbooks_integration_id = (
            SELECT id
            FROM quickbooks_integration
            WHERE company_id = tbl.company_id
        )
    """)

    for table in (
        'qbo_map_account_move',
        'qbo_map_account',
        'qbo_map_department',
        'qbo_map_inventory_adjustment',
        'qbo_map_partner',
        'qbo_map_payment_method',
        'qbo_map_payment',
        'qbo_map_product',
        'qbo_map_sale_order',
        'qbo_map_tax',
        'qbo_map_taxcode',
        'qbo_map_term',
    ):
        cr.execute(query.format(table=sql.Identifier(table)))

    # 2. Run job to refresh integration settings
    env = api.Environment(cr, SUPERUSER_ID, {})

    for qi in env['quickbooks.integration'].search([]):
        if qi.qb_access_granted:
            qi \
                .with_context(company_id=qi.company_id.id) \
                .with_delay(
                    description=f'[Migration 2.0.0] {qi.name}: Refresh QuickBooks Connection Settings',
                ) \
                .check_quickbooks_connection()
