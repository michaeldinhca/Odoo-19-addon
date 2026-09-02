# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSurveyFileUpload(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.survey = cls.env['survey.survey'].create({'title': 'File Upload Test Survey'})
        cls.question = cls.env['survey.question'].create({
            'survey_id': cls.survey.id,
            'title': 'Attach your file',
            'question_type': 'file_upload',
            'constr_mandatory': True,
            'constr_error_msg': 'This question requires an answer.',
        })
        cls.answer = cls.env['survey.user_input'].create({'survey_id': cls.survey.id})
        cls.attachment_1 = cls.env['ir.attachment'].create({'name': 'doc1.pdf', 'raw': b'%PDF-1.4 test'})
        cls.attachment_2 = cls.env['ir.attachment'].create({'name': 'doc2.pdf', 'raw': b'%PDF-1.4 test2'})

    def test_question_type_selection(self):
        self.assertEqual(self.question.question_type, 'file_upload')

    def test_max_size_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.question.file_upload_max_size_mb = 0

    def test_save_lines_creates_attachment_link(self):
        answer = f'{self.attachment_1.id},{self.attachment_2.id}'
        self.answer._save_lines(self.question, answer)
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.answer_type, 'file_upload')
        self.assertFalse(line.skipped)
        self.assertEqual(set(line.value_file_upload.ids), {self.attachment_1.id, self.attachment_2.id})

    def test_save_lines_empty_answer_is_skipped(self):
        self.answer._save_lines(self.question, '')
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(len(line), 1)
        self.assertTrue(line.skipped)
        self.assertFalse(line.value_file_upload)

    def test_save_lines_overwrite_replaces_attachments(self):
        self.answer._save_lines(self.question, str(self.attachment_1.id))
        self.answer._save_lines(self.question, str(self.attachment_2.id))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.value_file_upload.ids, [self.attachment_2.id])

    def test_mandatory_validation(self):
        errors = self.question.validate_question('')
        self.assertIn(self.question.id, errors)
        errors = self.question.validate_question(str(self.attachment_1.id))
        self.assertEqual(errors, {})

    def test_unlink_line_removes_attachment(self):
        self.answer._save_lines(self.question, str(self.attachment_1.id))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        attachment_id = self.attachment_1.id
        line.unlink()
        self.assertFalse(self.env['ir.attachment'].search([('id', '=', attachment_id)]))

    def test_unlink_response_removes_attachment(self):
        self.answer._save_lines(self.question, str(self.attachment_2.id))
        attachment_id = self.attachment_2.id
        self.answer.unlink()
        self.assertFalse(self.env['ir.attachment'].search([('id', '=', attachment_id)]))

    def test_display_name_shows_filenames_not_skipped(self):
        answer = f'{self.attachment_1.id},{self.attachment_2.id}'
        self.answer._save_lines(self.question, answer)
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertNotEqual(line.display_name, 'Skipped')
        self.assertIn('doc1.pdf', line.display_name)
        self.assertIn('doc2.pdf', line.display_name)

    def test_display_name_no_file_when_skipped(self):
        self.answer._save_lines(self.question, '')
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(line.display_name, 'Skipped')

    def test_file_upload_links_contains_download_url(self):
        self.attachment_1.generate_access_token()
        self.answer._save_lines(self.question, str(self.attachment_1.id))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertIn('/web/content/%s' % self.attachment_1.id, line.file_upload_links)
        self.assertIn(self.attachment_1.access_token, line.file_upload_links)
        self.assertIn('doc1.pdf', line.file_upload_links)
