# -*- coding: utf-8 -*-
import json

from odoo.tests.common import TransactionCase

# 1x1 transparent PNG, matching what the browser's canvas.toDataURL() would produce
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
DATA_URL = "data:image/png;base64," + PNG_B64


class TestSurveySignature(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.survey = cls.env['survey.survey'].create({'title': 'Signature Test Survey'})
        cls.question = cls.env['survey.question'].create({
            'survey_id': cls.survey.id,
            'title': 'Please sign',
            'question_type': 'signature',
            'constr_mandatory': True,
            'constr_error_msg': 'This question requires an answer.',
        })
        cls.answer = cls.env['survey.user_input'].create({'survey_id': cls.survey.id})

    def _posted(self, name, image_data_url):
        return json.dumps({'name': name, 'image': image_data_url})

    def test_question_type_selection(self):
        self.assertEqual(self.question.question_type, 'signature')

    def test_save_lines_creates_signature(self):
        self.answer._save_lines(self.question, self._posted('Jane Doe', DATA_URL))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.answer_type, 'signature')
        self.assertFalse(line.skipped)
        self.assertEqual(line.value_signature_name, 'Jane Doe')
        self.assertEqual(line.value_signature.decode(), PNG_B64)

    def test_save_lines_empty_answer_is_skipped(self):
        self.answer._save_lines(self.question, self._posted('', ''))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(len(line), 1)
        self.assertTrue(line.skipped)
        self.assertFalse(line.value_signature)

    def test_save_lines_blank_string_is_skipped(self):
        self.answer._save_lines(self.question, '')
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertTrue(line.skipped)

    def test_save_lines_overwrite_replaces_signature(self):
        self.answer._save_lines(self.question, self._posted('First', DATA_URL))
        self.answer._save_lines(self.question, self._posted('Second', DATA_URL))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.value_signature_name, 'Second')

    def test_mandatory_validation(self):
        errors = self.question.validate_question('')
        self.assertIn(self.question.id, errors)
        errors = self.question.validate_question(self._posted('Jane Doe', DATA_URL))
        self.assertEqual(errors, {})

    def test_display_name_shows_signer_not_skipped(self):
        self.answer._save_lines(self.question, self._posted('Jane Doe', DATA_URL))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(line.display_name, 'Jane Doe')

    def test_display_name_no_signature_when_skipped(self):
        self.answer._save_lines(self.question, self._posted('', ''))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        self.assertEqual(line.display_name, 'Skipped')

    def test_unlink_line_removes_attachment(self):
        self.answer._save_lines(self.question, self._posted('Jane Doe', DATA_URL))
        line = self.env['survey.user_input.line'].search([
            ('user_input_id', '=', self.answer.id),
            ('question_id', '=', self.question.id),
        ])
        line_id = line.id
        line.unlink()
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'survey.user_input.line'),
            ('res_id', '=', line_id),
            ('res_field', '=', 'value_signature'),
        ])
        self.assertFalse(attachment)
