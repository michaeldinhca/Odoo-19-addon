# -*- coding: utf-8 -*-
{
    'name': 'Survey File Upload',
    'version': '19.0.1.2.0',
    'category': 'Marketing/Surveys',
    'summary': 'Adds a "File Upload" question type to Survey, with AJAX (non-blocking) upload',
    'description': """
Survey File Upload
===================
Adds a genuinely new "File Upload" question type to the Survey app, so respondents
can attach one or more files as their answer to a question.

Features (v1):
--------------
* New "File Upload" question type, selectable alongside the stock types.
* Per-question configurable maximum file size (MB) and single/multiple file toggle.
* Non-blocking AJAX upload: files are sent to the server and attached to the
  response as soon as they're picked, independent of the page-submit flow.
* A real upload progress bar (0-100%, from actual bytes sent, not a fake
  animation) so respondents can tell a large file is still going up rather
  than wondering if the upload silently failed.
* Respects the existing "Mandatory Answer" constraint like every other question type.
* Uploaded files are listed (with download links) on the results page for each
  respondent's answer, and on the response's own Answers tab in the backend.
* Uploaded attachments are cleaned up automatically when an answer or a whole
  response is deleted, so removed responses don't leave orphaned files behind.

This module was built from scratch against Odoo 19's survey app (jsonrpc routes,
the Interaction frontend framework, string-expression view attributes) — it is not
a port of any third-party module.
""",
    'author': 'Michael Dinh',
    'license': 'LGPL-3',
    'depends': ['survey'],
    'data': [
        'views/survey_question_views.xml',
        'views/survey_templates.xml',
        'views/survey_templates_statistics.xml',
        'views/survey_user_views.xml',
    ],
    'assets': {
        'survey.survey_assets': [
            'survey_file_upload/static/src/interactions/survey_file_upload.js',
            'survey_file_upload/static/src/interactions/survey_form_patch.js',
            'survey_file_upload/static/src/scss/survey_file_upload.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
