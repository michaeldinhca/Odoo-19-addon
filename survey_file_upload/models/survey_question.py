# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SurveyQuestion(models.Model):
    _inherit = 'survey.question'

    question_type = fields.Selection(
        selection_add=[('file_upload', 'File Upload')],
        ondelete={'file_upload': lambda records: records.write({'question_type': 'simple_choice'})},
    )
    file_upload_max_size_mb = fields.Integer(
        string='Max File Size (MB)', default=10,
        help="Maximum size, in MB, accepted per uploaded file.")
    file_upload_multiple = fields.Boolean(
        string='Allow Multiple Files',
        help="If checked, respondents can attach more than one file to this question.")

    @api.constrains('question_type', 'file_upload_max_size_mb')
    def _check_file_upload_max_size(self):
        for question in self:
            if question.question_type == 'file_upload' and question.file_upload_max_size_mb <= 0:
                raise ValidationError(_('The maximum file size must be greater than 0 MB.'))
