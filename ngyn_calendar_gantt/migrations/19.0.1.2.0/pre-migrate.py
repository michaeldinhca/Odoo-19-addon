# -*- coding: utf-8 -*-
"""
19.0.1.2.0 removes the custom x_ngyn_installer_ids field (calendar.event ->
res.partner) in favor of the native calendar.event.partner_ids (Attendees).
Before the field disappears, copy any existing assignments onto Attendees so
databases that already used it (e.g. seeded demo data) don't silently lose
that information. Safe on a fresh install (old table never existed) and safe
to run twice (ON CONFLICT DO NOTHING).
"""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('ngyn_calendar_event_installer_rel')")
    if not cr.fetchone()[0]:
        return

    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'calendar_event_res_partner_rel'
        ORDER BY ordinal_position
        """
    )
    columns = [row[0] for row in cr.fetchall()]
    if len(columns) != 2:
        return

    event_col, partner_col = columns
    if "partner" in event_col:
        event_col, partner_col = partner_col, event_col

    cr.execute(
        f"""
        INSERT INTO calendar_event_res_partner_rel ({event_col}, {partner_col})
        SELECT event_id, partner_id FROM ngyn_calendar_event_installer_rel
        ON CONFLICT DO NOTHING
        """
    )
