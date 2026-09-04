# -*- coding: utf-8 -*-
from odoo import fields, models


class SurveyQuestion(models.Model):
    _inherit = 'survey.question'

    question_type = fields.Selection(
        selection_add=[('signature', 'Signature')],
        ondelete={'signature': lambda records: records.write({'question_type': 'simple_choice'})},
    )
