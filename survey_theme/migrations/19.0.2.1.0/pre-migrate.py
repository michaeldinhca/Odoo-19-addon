# -*- coding: utf-8 -*-
"""Replace the boolean use_custom_theme (1.x/2.0.x) with the theme_style selection field.

Runs pre-migrate (before the ORM's own new-field default-fill) so existing surveys keep
their actual on/off state instead of every row silently reverting to theme_style's default
('indigo'). A fresh install has no use_custom_theme column, so this is a no-op there.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'survey_survey' AND column_name = 'use_custom_theme'
    """)
    if not cr.fetchone():
        return

    cr.execute("ALTER TABLE survey_survey ADD COLUMN IF NOT EXISTS theme_style varchar")
    cr.execute("""
        UPDATE survey_survey
        SET theme_style = CASE WHEN use_custom_theme THEN 'indigo' ELSE 'none' END
        WHERE theme_style IS NULL
    """)
    cr.execute("ALTER TABLE survey_survey DROP COLUMN use_custom_theme")
