# -*- coding: utf-8 -*-
from odoo import fields, models


class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    use_custom_theme = fields.Boolean(
        string='Use Survey Theme', default=True,
        help="Applies the restyled look (colors, spacing, company logo) to this survey's "
             "taking flow. Turn off to use the stock Odoo Survey appearance instead.")
