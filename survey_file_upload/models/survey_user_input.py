# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    def _save_lines(self, question, answer, comment=None, overwrite_existing=True):
        if question.question_type != 'file_upload':
            return super()._save_lines(question, answer, comment=comment, overwrite_existing=overwrite_existing)

        old_answers = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.id),
            ('question_id', '=', question.id),
        ])
        if old_answers and not overwrite_existing:
            raise UserError(_("This answer cannot be overwritten."))
        return self._save_line_simple_answer(question, old_answers, answer)

    def _get_line_answer_values(self, question, answer, answer_type):
        if answer_type != 'file_upload':
            return super()._get_line_answer_values(question, answer, answer_type)

        vals = {
            'user_input_id': self.id,
            'question_id': question.id,
            'skipped': False,
            'answer_type': answer_type,
        }
        attachment_ids = [int(value) for value in (answer or '').split(',') if value]
        if not attachment_ids:
            vals.update(answer_type=None, skipped=True)
        else:
            vals['value_file_upload'] = [(6, 0, attachment_ids)]
        return vals

    def unlink(self):
        # user_input_line_ids cascades at the DB level on unlink (ondelete='cascade' on its
        # user_input_id many2one), which bypasses SurveyUserInputLine.unlink() below — so the
        # attachments it would have cleaned up must be collected here, before that happens.
        attachments = self.user_input_line_ids.filtered(
            lambda line: line.answer_type == 'file_upload').value_file_upload
        result = super().unlink()
        attachments.sudo().unlink()
        return result


class SurveyUserInputLine(models.Model):
    _inherit = 'survey.user_input.line'

    answer_type = fields.Selection(
        selection_add=[('file_upload', 'Uploaded File')],
        ondelete={'file_upload': 'cascade'},
    )
    value_file_upload = fields.Many2many(
        'ir.attachment', 'survey_user_input_line_file_upload_rel', 'line_id', 'attachment_id',
        string='Uploaded Files')

    def unlink(self):
        attachments = self.filtered(lambda line: line.answer_type == 'file_upload').value_file_upload
        result = super().unlink()
        attachments.sudo().unlink()
        return result
