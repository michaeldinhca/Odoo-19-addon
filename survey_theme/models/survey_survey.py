# -*- coding: utf-8 -*-
from odoo import fields, models


class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    # New theme styles just add a selection_add value (own module, e.g. a future
    # survey_theme_XXX depending on this one) or a value here directly - see CLAUDE.md
    # for the .o_survey_theme_custom / .o_survey_theme_<style> split this relies on.
    theme_style = fields.Selection([
        ('none', 'Stock Odoo'),
        ('indigo', 'Indigo (Modern)'),
    ], string='Theme', default='indigo', required=True,
        help="Restyles this survey's taking flow (colors, spacing, shapes, company logo). "
             "'Stock Odoo' keeps the default appearance.")
