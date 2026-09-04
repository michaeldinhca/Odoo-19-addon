# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

## [1.0.1] - 2026-09-04

### Fixed
- **The signature didn't show up on the respondent-facing "Review your
  answers" page** - only the question title appeared, nothing underneath.
  Root cause: that page (`survey.survey_page_print`) is a separate template
  from `survey.question_container` with its own closed per-question-type
  dispatch chain - `signature` just wasn't in it (same root cause hit
  `survey_file_upload`'s file listing there too). Added
  `views/survey_templates_print.xml` to hook that template too (shows the
  signature image and signer name, or "This question was skipped").

## [1.0.0] - 2026-09-03

### Added
- New "Signature" question type for Survey.
- Signing UI is Odoo's own core `web.NameAndSignature` component, mounted via
  the `owl-component` public-component mechanism (the same one
  `portal.signature_form` uses for signing a quotation) - not a copy or a
  reimplementation of that component's code.
- `survey.user_input.line.value_signature` (Binary, `attachment=True`) and
  `value_signature_name` (Char) store the captured PNG and the typed
  signer name.
- Mandatory-answer validation, results-page rendering, and backend Answers
  tab display for the new question type.
