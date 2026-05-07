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
