# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    def _save_lines(self, question, answer, comment=None, overwrite_existing=True):
        if question.question_type != 'signature':
            return super()._save_lines(question, answer, comment=comment, overwrite_existing=overwrite_existing)

        old_answers = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.id),
            ('question_id', '=', question.id),
        ])
        if old_answers and not overwrite_existing:
            raise UserError(_("This answer cannot be overwritten."))
        return self._save_line_simple_answer(question, old_answers, answer)

    def _get_line_answer_values(self, question, answer, answer_type):
        if answer_type != 'signature':
            return super()._get_line_answer_values(question, answer, answer_type)

        vals = {
            'user_input_id': self.id,
            'question_id': question.id,
            'skipped': False,
            'answer_type': answer_type,
        }
        try:
            data = json.loads(answer) if answer else {}
        except ValueError:
            data = {}
        # the widget posts a data URL ("data:image/png;base64,<payload>") - only the
        # payload is stored, matching how a plain Binary field expects its value
        image_data_url = (data.get('image') or '').strip()
        if not image_data_url:
            vals.update(answer_type=None, skipped=True)
        else:
            vals['value_signature'] = image_data_url.split(',', 1)[-1]
            vals['value_signature_name'] = (data.get('name') or '').strip()
        return vals


class SurveyUserInputLine(models.Model):
    _inherit = 'survey.user_input.line'

    answer_type = fields.Selection(
        selection_add=[('signature', 'Signature')],
        ondelete={'signature': 'cascade'},
    )
    # attachment=True: Odoo stores/cleans up this image as its own ir.attachment
    # (res_model='survey.user_input.line', res_id=this line) automatically, tied to this
    # line's own lifecycle - core's unlink() already sweeps it, no custom cleanup needed
    # (see survey_file_upload's CLAUDE.md for the redundant-unlink mistake this avoids).
    value_signature = fields.Binary('Signature Image', attachment=True)
    value_signature_name = fields.Char('Signed By')

    @api.depends('answer_type', 'value_signature_name', 'value_signature')
    def _compute_display_name(self):
        super()._compute_display_name()
        for line in self:
            if line.answer_type == 'signature':
                if not line.value_signature:
                    line.display_name = _('No Signature')
                else:
                    line.display_name = line.value_signature_name or _('Signed')
