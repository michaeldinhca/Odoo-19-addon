# -*- coding: utf-8 -*-
{
    'name': 'Survey Theme',
    'version': '19.0.2.1.0',
    'category': 'Marketing/Surveys',
    'summary': 'Restyles the Survey taking flow: mobile-first, company logo, long-text-safe choices',
    'description': """
Survey Theme
============
A pure front-end restyle of the Survey app's respondent-facing taking flow
(start screen, every question type, progress bar/navigation, completion
screen) - no behavior changes, works with any `questions_layout` setting
(one page, one section per page, one question per page).

Features (v1):
--------------
* Per-survey **Theme** selection (Options tab, next to the questions-layout
  settings) - each survey independently chooses "Stock Odoo" or a themed
  style. Ships with one style ("Indigo") for now; built to grow into a
  real picker as more styles are added (new selection value + its own
  scoped SCSS block - see CLAUDE.md).
* Company logo shown on the survey taking page header.
* Modern accent color / rounded shape language.
* Fixes long answer-option text (simple/multiple choice) wrapping badly
  against the selection icon - the icon now sits beside the text instead
  of fighting it via floats, purely via a flex-layout override; no
  template or JS changes to the choice-rendering logic.
* Wider spacing between answer options, a card treatment for the active
  question, and a horizontally-scrollable matrix table on narrow screens.
* If `survey_file_upload` is also installed, its upload widget (dropzone,
  upload button, uploaded-file chip, progress bar) picks up the same
  accent color and shape language automatically.

This does not touch the backend survey builder or the results/statistics
pages - taking-flow only.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['survey'],
    'data': [
        'views/survey_survey_views.xml',
        'views/survey_templates.xml',
    ],
    'assets': {
        'survey.survey_assets': [
            'survey_theme/static/src/scss/survey_theme.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
