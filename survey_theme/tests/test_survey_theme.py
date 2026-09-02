# -*- coding: utf-8 -*-
from odoo.tests.common import HttpCase


class TestSurveyTheme(HttpCase):

    def _make_survey(self, use_custom_theme):
        survey = self.env['survey.survey'].create({
            'title': 'Theme Toggle Test',
            'access_mode': 'public',
            'users_login_required': False,
            'use_custom_theme': use_custom_theme,
        })
        self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Your name',
            'question_type': 'char_box',
        })
        return survey

    def test_theme_class_present_when_enabled(self):
        survey = self._make_survey(True)
        response = self.url_open('/survey/start/%s' % survey.access_token, timeout=30)
        self.assertIn('o_survey_theme_custom', response.text)

    def test_theme_class_absent_when_disabled(self):
        survey = self._make_survey(False)
        response = self.url_open('/survey/start/%s' % survey.access_token, timeout=30)
        self.assertNotIn('o_survey_theme_custom', response.text)

    def test_use_custom_theme_defaults_true(self):
        survey = self.env['survey.survey'].create({'title': 'Default Test'})
        self.assertTrue(survey.use_custom_theme)
