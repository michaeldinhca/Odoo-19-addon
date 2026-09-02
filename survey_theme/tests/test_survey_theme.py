# -*- coding: utf-8 -*-
from odoo.tests.common import HttpCase


class TestSurveyTheme(HttpCase):

    def _make_survey(self, theme_style):
        survey = self.env['survey.survey'].create({
            'title': 'Theme Selection Test',
            'access_mode': 'public',
            'users_login_required': False,
            'theme_style': theme_style,
        })
        self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Your name',
            'question_type': 'char_box',
        })
        return survey

    def test_theme_classes_present_for_indigo(self):
        survey = self._make_survey('indigo')
        response = self.url_open('/survey/start/%s' % survey.access_token, timeout=30)
        self.assertIn('o_survey_theme_custom', response.text)
        self.assertIn('o_survey_theme_indigo', response.text)

    def test_theme_classes_absent_for_none(self):
        survey = self._make_survey('none')
        response = self.url_open('/survey/start/%s' % survey.access_token, timeout=30)
        self.assertNotIn('o_survey_theme_custom', response.text)
        self.assertNotIn('o_survey_theme_indigo', response.text)

    def test_theme_style_defaults_indigo(self):
        survey = self.env['survey.survey'].create({'title': 'Default Test'})
        self.assertEqual(survey.theme_style, 'indigo')
