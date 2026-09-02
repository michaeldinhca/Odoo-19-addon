# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import api, fields, models
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
    file_upload_links = fields.Html(
        'Uploaded Files (Download)', compute='_compute_file_upload_links', sanitize=False)

    @api.depends('answer_type', 'value_file_upload.name', 'value_file_upload.access_token')
    def _compute_display_name(self):
        super()._compute_display_name()
        for line in self:
            if line.answer_type == 'file_upload':
                line.display_name = ', '.join(line.value_file_upload.mapped('name')) or _('No File')

    @api.depends('value_file_upload.name', 'value_file_upload.access_token')
    def _compute_file_upload_links(self):
        for line in self:
            if not line.value_file_upload:
                line.file_upload_links = False
                continue
            links = [
                Markup('<a href="/web/content/%s?access_token=%s&amp;download=true" target="_blank">%s</a>') % (
                    attachment.id, attachment.access_token, escape(attachment.name))
                for attachment in line.value_file_upload
            ]
            line.file_upload_links = Markup('<br/>').join(links)

    def unlink(self):
        attachments = self.filtered(lambda line: line.answer_type == 'file_upload').value_file_upload
        result = super().unlink()
        attachments.sudo().unlink()
        return result
