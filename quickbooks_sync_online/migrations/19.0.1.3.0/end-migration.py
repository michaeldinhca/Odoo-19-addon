# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).


def migrate(cr, version):

    # Set QuickBooks excluded flag on all invoices that have a mapping record
    cr.execute(
        """
            UPDATE account_move AS am
            SET is_excluded_from_qbo_sync = TRUE
            FROM qbo_map_account_move AS qm
            WHERE qm.invoice_id = am.id
        """
    )

    # Set QuickBooks excluded flag on all payments that have a mapping record
    cr.execute(
        """
            UPDATE account_payment AS ap
            SET is_excluded_from_qbo_sync = TRUE
            FROM qbo_map_payment AS qp
            WHERE qp.payment_id = ap.id
        """
    )
