# -*- coding: utf-8 -*-
"""
data/knowledge_articles.xml used to grant the admin write-access member via an
inline `article_member_ids` eval with a (0, 0, {...}) create command. That form
re-issues a create() every time the data file is re-applied (i.e. on every
module upgrade, not just the first install), which crashes with a
UniqueViolation on knowledge_article_member_unique_article_partner once the
member row already exists from a prior install.

The fix is to track that member row as its own top-level <record> with a
stable external ID, so future upgrades match it by xmlid and write() instead
of create(). But a database already past the broken version has a member row
with no xmlid at all -- this migration adopts that existing row under the new
external ID before the data file loads, so the upgrade into this version (and
every one after it) updates in place instead of colliding.
"""


def migrate(cr, version):
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s",
        ("ngyn_resource_planning", "knowledge_article_ngyn_rp_root"),
    )
    row = cr.fetchone()
    if not row:
        return  # module was never fully installed before; nothing to adopt
    article_id = row[0]

    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s",
        ("base", "partner_admin"),
    )
    row = cr.fetchone()
    if not row:
        return
    partner_id = row[0]

    cr.execute(
        "SELECT id FROM knowledge_article_member WHERE article_id = %s AND partner_id = %s LIMIT 1",
        (article_id, partner_id),
    )
    row = cr.fetchone()
    if not row:
        return  # no pre-existing member row to adopt; the data file will create one fresh
    member_id = row[0]

    cr.execute(
        """
        INSERT INTO ir_model_data (name, module, model, res_id, noupdate)
        SELECT %s, %s, %s, %s, false
        WHERE NOT EXISTS (
            SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s
        )
        """,
        (
            "knowledge_article_member_ngyn_rp_admin",
            "ngyn_resource_planning",
            "knowledge.article.member",
            member_id,
            "ngyn_resource_planning",
            "knowledge_article_member_ngyn_rp_admin",
        ),
    )
