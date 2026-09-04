# -*- coding: utf-8 -*-
{
    'name': 'Survey Signature',
    'version': '19.0.1.0.1',
    'category': 'Marketing/Surveys',
    'summary': 'Adds a "Signature" question type to Survey, using Odoo\'s own signature pad UI',
    'description': """
Survey Signature
==================
Adds a genuinely new "Signature" question type to the Survey app, so
respondents can sign directly on the survey page as their answer.

Features (v1):
--------------
* New "Signature" question type, selectable alongside the stock types.
* Reuses Odoo's own core signature-pad component (`web.NameAndSignature`) -
  the exact same "Auto / Draw / Load" signing widget used to sign a
  quotation or invoice on the customer portal - so respondents get a
  familiar experience, not a re-invented one. Type a name for an
  auto-generated cursive signature, draw with mouse/touch, or upload an
  image of a signature.
* Respects the existing "Mandatory Answer" constraint like every other
  question type.
* Signature image and signer name are shown on the results page for each
  respondent's answer, and on the response's own Answers tab in the backend.

Built by wiring Odoo's own core `web.NameAndSignature` OWL component into a
new survey question type via the `owl-component` public-component mounting
mechanism - the same mechanism `portal.signature_form` uses to let customers
sign a quotation on the portal. This is not a reimplementation or a port of
any third-party module; it reuses Odoo Community's own signature widget.
""",
    'author': 'NGYN Solutions Inc.',
    'website': 'https://ngynsolutions.com',
    'license': 'LGPL-3',
    'depends': ['survey'],
    'data': [
        'views/survey_question_views.xml',
        'views/survey_templates.xml',
        'views/survey_templates_statistics.xml',
        'views/survey_templates_print.xml',
        'views/survey_user_views.xml',
    ],
    'assets': {
        'survey.survey_assets': [
            'survey_signature/static/src/components/survey_signature.js',
            'survey_signature/static/src/components/survey_signature.xml',
            'survey_signature/static/src/components/survey_signature.scss',
            'survey_signature/static/src/interactions/survey_form_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
