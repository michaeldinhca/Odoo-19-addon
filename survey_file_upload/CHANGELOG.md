# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

## [1.2.2] - 2026-09-04

### Fixed
- **Uploaded files didn't show up on the respondent-facing "Review your
  answers" page** - only the question title appeared, nothing underneath.
  Root cause: that page (`survey.survey_page_print`) is a separate template
  from `survey.question_container` with its own closed per-question-type
  dispatch chain, unrelated to the one this module already hooked for the
  live taking flow and the backend results page - `file_upload` just wasn't
  in it. Added `views/survey_templates_print.xml` to hook that template too
  (lists the uploaded file name(s), or "This question was skipped").

## [1.2.1] - 2026-09-02

### Changed
- Module author/copyright attribution changed to NGYN Solutions Inc.
  (`https://ngynsolutions.com`), matching this repo's other original
  modules (e.g. `ngyn_resource_planning`) rather than an individual name.

## [1.2.0] - 2026-09-02

### Added
- **Real upload progress bar.** The upload previously only showed a static
  "Uploading..." label with no indication of how far along it was, or
  whether it had stalled. `fetch()` has no upload-progress event, so
  `survey_file_upload.js` now uses `XMLHttpRequest` with
  `xhr.upload.onprogress` for the upload call specifically (`onRemoveClick`'s
  delete call is unchanged, still `fetch()` - it's a tiny request with
  nothing to show progress on). The bar reflects actual bytes sent, not a
  fake animation, and the trigger button is disabled for the duration so a
  second click can't start a second upload mid-flight.

## [1.1.1] - 2026-09-02

### Fixed
- **Deleting a `survey.user_input` (a whole response) raised `MissingError`
  on its uploaded attachment(s).** `SurveyUserInput.unlink()` (added in 1.0.0)
  collected the response's file attachments, called `super().unlink()`, then
  tried to unlink those attachments itself — but Odoo's core
  `BaseModel.unlink()` already auto-deletes any `ir.attachment` whose
  `res_model`/`res_id` point at the record being deleted, and these
  attachments use `res_model='survey.user_input'` — so core had already
  removed them by the time this module's own cleanup ran a second time.
  Caught deleting a real (non-test) response created while reproducing the
  1.1.0 "Skipped" report against a live deployment. Fixed by removing the
  redundant override entirely — core already handles this case for free.
  `SurveyUserInputLine.unlink()` is unaffected and still needed (see
  `CLAUDE.md`): its attachments' `res_model` is the *response*, not the
  line, so deleting a line directly isn't covered by core's sweep.

## [1.1.0] - 2026-09-02

### Fixed
- **Backend "Answers" tab always showed "Skipped" for file-upload answers, even
  when the upload succeeded and the attachment was correctly linked.** Root
  cause: that tab's "Answer" column displays `survey.user_input.line.display_name`,
  and `_compute_display_name()` was never extended for the new `file_upload`
  answer type — it fell through to the base method's generic "not otherwise
  recognized" fallback, which is literally the string "Skipped". The save path
  itself was never affected (`skipped=False`, `value_file_upload` populated
  correctly all along) — confirmed via automated browser reproduction
  (page-per-question, one-page, and the exact multi-question layout this was
  first reported against) run both locally and directly against a live
  deployment, all of which saved correctly; only the *label* was wrong.
  `_compute_display_name()` now lists the uploaded filename(s) instead.

### Added
- `survey.user_input.line.file_upload_links` (Html, computed): direct
  `/web/content/<id>?access_token=...&download=true` download links per
  attachment. Shown both on the response's own "Answers" tab (as an
  otherwise-hidden column, only visible for file-upload rows) and on the
  individual line's technical form view — not just the aggregate results page,
  which already had download links via `question_result_file_upload`.

## [1.0.0] - 2026-09-02

Initial release, built from scratch against Odoo 19 Community's actual `survey`
addon source (see `CLAUDE.md` for why this isn't a port of the v16 third-party
module it was scoped from).

### Added
- `survey.question.question_type` gains a `file_upload` value, with
  `file_upload_max_size_mb` (default 10) and `file_upload_multiple` fields
  shown on the Options tab when that type is selected.
- `survey.user_input.line` gains `answer_type = 'file_upload'` and a
  `value_file_upload` many2many to `ir.attachment`.
- `/survey/file_upload/<survey_token>/<answer_token>/<question_id>` and
  `/survey/file_upload/delete/<survey_token>/<answer_token>/<attachment_id>` —
  token-gated multipart upload/delete routes, independent of the jsonrpc
  `/survey/submit` flow (which cannot carry file bytes).
- Frontend: a dropzone/upload-button widget (own `Interaction`, registered
  under `survey.survey_assets`) plus a `patch()` of `SurveyForm` to fold the
  file question's value into the existing submit-values/validation switch
  statements.
- Backend results page: uploaded files are listed with download links per
  respondent, via an inherited `question_result_file_upload` template.
- Attachment cleanup on `survey.user_input.line.unlink()` and
  `survey.user_input.unlink()` (the latter needed because
  `user_input_line_ids` cascades at the DB level and bypasses the line's own
  `unlink()`).
- Basic test coverage (`tests/test_survey_file_upload.py`): question type
  availability, the max-size constraint, save/overwrite/skip behavior of
  `_save_lines`, mandatory validation, and attachment cleanup on unlink.

### Known limitations (v1)
- No client-side drag-and-drop (only click-to-browse) — see `CLAUDE.md`.
- No results-page pagination for file-upload answers (other text-type results
  paginate via `question_table_pagination`; this type doesn't yet).
- No admin-side bulk download (zip) of all files submitted for a question.
