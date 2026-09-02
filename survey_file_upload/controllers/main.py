# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.addons.survey.controllers.main import Survey
from odoo.http import request


class SurveyFileUploadController(Survey):
    """ Out-of-band (AJAX) upload/delete endpoints for the 'file_upload' question type.

    Files are uploaded/removed independently of the page-submit flow (which is JSON-RPC
    and cannot carry multipart bytes) - the frontend keeps a hidden input with the
    comma-separated ids of whatever is currently attached, and that string is what
    actually gets posted as the question's "answer" on /survey/submit.
    """

    def _get_file_upload_access(self, survey_token, answer_token):
        """ Resolve+validate token access, mirroring the checks /survey/submit itself applies.

        :return: (error_response or None, survey_sudo, answer_sudo)
        """
        access_data = self._get_access_data(survey_token, answer_token, ensure_token=True)
        if access_data['validity_code'] is not True:
            return request.make_json_response({'error': _('Access denied.')}, status=403), None, None
        answer_sudo = access_data['answer_sudo']
        if answer_sudo.state == 'done':
            return request.make_json_response({'error': _('This survey is no longer open for answers.')}, status=403), None, None
        return None, access_data['survey_sudo'], answer_sudo

    def _get_file_upload_question(self, survey_sudo, question_id):
        question_sudo = request.env['survey.question'].sudo().browse(question_id)
        if not question_sudo.exists() or question_sudo.survey_id != survey_sudo or question_sudo.question_type != 'file_upload':
            return None
        return question_sudo

    @http.route(
        '/survey/file_upload/<string:survey_token>/<string:answer_token>/<int:question_id>',
        type='http', auth='public', website=True, methods=['POST'])
    def survey_file_upload(self, survey_token, answer_token, question_id, **post):
        error_response, survey_sudo, answer_sudo = self._get_file_upload_access(survey_token, answer_token)
        if error_response:
            return error_response

        question_sudo = self._get_file_upload_question(survey_sudo, question_id)
        if question_sudo is None:
            return request.make_json_response({'error': _('Invalid question.')}, status=400)

        files = request.httprequest.files.getlist('ufile')
        if not files:
            return request.make_json_response({'error': _('No file received.')}, status=400)

        if not question_sudo.file_upload_multiple:
            existing_line = request.env['survey.user_input.line'].sudo().search([
                ('user_input_id', '=', answer_sudo.id),
                ('question_id', '=', question_sudo.id),
            ], limit=1)
            existing_count = len(existing_line.value_file_upload) if existing_line else 0
            if existing_count + len(files) > 1:
                return request.make_json_response(
                    {'error': _('Only one file is allowed for this question.')}, status=400)

        max_bytes = question_sudo.file_upload_max_size_mb * 1024 * 1024
        uploaded, errors = [], []
        for ufile in files:
            content = ufile.read()
            if len(content) > max_bytes:
                errors.append(_('"%(filename)s" exceeds the %(limit)s MB limit.', filename=ufile.filename,
                                 limit=question_sudo.file_upload_max_size_mb))
                continue
            attachment_sudo = request.env['ir.attachment'].sudo().create({
                'name': ufile.filename,
                'raw': content,
                'res_model': 'survey.user_input',
                'res_id': answer_sudo.id,
                'public': False,
            })
            attachment_sudo.generate_access_token()
            uploaded.append({
                'id': attachment_sudo.id,
                'name': attachment_sudo.name,
                'size': attachment_sudo.file_size,
                'access_token': attachment_sudo.access_token,
            })

        return request.make_json_response({'files': uploaded, 'errors': errors})

    @http.route(
        '/survey/file_upload/delete/<string:survey_token>/<string:answer_token>/<int:attachment_id>',
        type='http', auth='public', website=True, methods=['POST'])
    def survey_file_upload_delete(self, survey_token, answer_token, attachment_id, **post):
        error_response, survey_sudo, answer_sudo = self._get_file_upload_access(survey_token, answer_token)
        if error_response:
            return error_response

        attachment_sudo = request.env['ir.attachment'].sudo().browse(attachment_id)
        if not attachment_sudo.exists() \
                or attachment_sudo.res_model != 'survey.user_input' \
                or attachment_sudo.res_id != answer_sudo.id:
            return request.make_json_response({'error': _('File not found.')}, status=404)

        attachment_sudo.unlink()
        return request.make_json_response({'success': True})
