# CLAUDE.md — context for AI coding assistants

Read this first. It's written so a fresh AI session (Claude Code, or any other
coding assistant) can understand what this module is, why it's built the way
it is, and what to do next — without re-deriving context from the code alone.

## What this is

An Odoo 19 Community addon (`survey_file_upload`) that adds a new **File
Upload** question type to the stock Survey app — respondents can attach one or
more files as their answer, with a configurable per-question max size and
single/multiple toggle, uploaded via AJAX independent of the page-submit flow.

## Why this exists, and why it's a clean-room build

The feature scope was taken from a paid Odoo 16 third-party module,
`bt_survey_ajax_upload_file` by Banas Tech (OPL-1 licensed — its terms
explicitly forbid publishing, distributing, or sublicensing the software or
modified copies of it). This repo is public, so **none of that module's code
was ported, copied, or referenced while writing this one** — only its
*end-user feature description* (from the Odoo Apps listing) was used to scope
what to build. Every model/controller/template/JS file here was designed and
written directly against Odoo 19's actual `survey` addon source. If you're
asked to "add parity with the old module" or similar, that means matching
end-user behavior, not reaching for the v16 module's code — it isn't in this
repo and shouldn't be.

## Non-obvious things worth knowing before you touch the code

- **The upload call uses `XMLHttpRequest`, not `fetch()` — deliberately.**
  `fetch()` has no upload-progress event (only a download-side
  `ReadableStream`, which doesn't help here); `XMLHttpRequest.upload`'s
  `progress` event is the only browser API that reports bytes actually sent,
  which is what the progress bar in `survey_file_upload.js`
  (`_uploadWithProgress`) is built on. The delete call
  (`onRemoveClick`) is still plain `fetch()` — it's a small request with
  nothing meaningful to show progress on, so there's no reason to carry the
  extra complexity there too.

- **The stock `survey` module has no extensibility hook for new question
  types.** `question_type`/`answer_type` dispatch is a series of closed
  `if/elif` chains and `switch` statements scattered across
  `survey.question`, `survey.user_input`, `survey.user_input.line`, the
  results-page QWeb template, and the frontend JS. Adding a type means
  auditing and extending each of these individually — there's no single
  interface to implement. See the method-by-method extension points below.

- **v19 changed the page-submit route to `type='jsonrpc'`** (was `type='json'`
  in older versions) — and a jsonrpc endpoint can't carry multipart file
  bytes. That's *why* this module has its own separate `type='http'` upload
  route (`controllers/main.py`) instead of extending `/survey/submit`
  directly: files go up out-of-band as soon as they're picked, and only the
  resulting attachment id(s) — as a comma-joined string — get folded into the
  normal jsonrpc submit payload for that question, via a hidden input the
  frontend keeps in sync.

- **The frontend taking-form is server-rendered QWeb, not OWL components per
  question type.** The JS layer (`@web/public/interaction`'s `Interaction`
  framework, not the old `publicWidget`) enhances that HTML; question-type
  dispatch on the client is two `switch` statements in the stock
  `survey_form.js` (`validateForm`, `prepareSubmitValues`), keyed off a
  `data-question-type` attribute the QWeb template sets. This module doesn't
  edit that core file — it can't, it's not this module's file — it uses OWL's
  `patch()` (`static/src/interactions/survey_form_patch.js`) to extend both
  switches. If a stock Odoo upgrade changes those two methods' shape, this
  patch needs re-checking against the new version.

- **Prior answers are prefilled by server-side QWeb, not a client AJAX
  fetch.** Each page navigation is a full server render, so
  `views/survey_templates.xml`'s `question_file_upload` template just reads
  `answer_lines[0].value_file_upload` directly (same pattern every stock
  question template uses for its own value field) — no separate "prefill"
  endpoint was needed (the v16 module this was scoped from had one; v19's
  render model makes it unnecessary).

- **Attachment storage/access**: uploaded files are `ir.attachment` records
  with `res_model='survey.user_input', res_id=<the response>` (not
  `survey.user_input.line` — that record doesn't exist yet at upload time,
  since lines are only created at final page-submit) and their own generated
  `access_token`, so results-page download links use the native
  `/web/content/<id>?access_token=...` mechanism rather than a custom
  download route.

- **Attachment cleanup needs exactly one `unlink()` override, on the line —
  not on `survey.user_input` too.** Odoo's core `BaseModel.unlink()` already
  auto-deletes any `ir.attachment` whose `res_model`/`res_id` point at a
  record being deleted (see `odoo/orm/models.py`, the `ir_attachment_unlink`
  sweep) — and these attachments are stored with
  `res_model='survey.user_input'` (see below), so deleting a whole response
  is *already* handled by core, for free. An earlier version of this module
  added a redundant `SurveyUserInput.unlink()` that re-collected and
  re-deleted the same attachments after `super().unlink()` — which crashed
  with `MissingError` in production, since core had already removed them by
  then (caught deleting a live test response on a real deployment; see
  CHANGELOG 1.1.1). `SurveyUserInputLine.unlink()` is still needed, though:
  deleting a single *line* (e.g. from the backend list view, or a choice/
  matrix question's old-answer replacement) doesn't match `res_model='survey.user_input.line'`
  in core's sweep (the attachment's `res_model` is the parent response, not
  the line), so that path needs the explicit cleanup this module provides.
  If you're tempted to add cleanup on `survey.user_input.unlink()` again,
  don't — check core's behavior for the model/res_id you're actually using
  first.

- **Replacing an already-uploaded file doesn't leak an orphan**, because the
  frontend widget's "remove" action calls the real delete route immediately
  (not just a local UI un-check) — by the time a page is re-submitted, the
  hidden input's id list already matches exactly what should remain, so
  `_get_line_answer_values`'s M2M-replace-on-write never needs to reconcile
  a stale id itself.

- **The mandatory-answer check needed no override.** The base
  `validate_question()` already does a generic "empty answer + mandatory +
  not in [simple_choice, multiple_choice]" check before dispatching to any
  per-type validator — file_upload's answer is a plain string (comma-joined
  ids, or `''`), so it falls into that generic path for free.
  `models/survey_question.py` deliberately does **not** override
  `validate_question()` — don't add one unless a real per-type validation
  rule (beyond mandatory) is needed.

- **`_compute_display_name()` needed a `file_upload` branch too** — easy to
  miss since it doesn't affect saving/validation at all, only *display*. The
  base method's fallback for any answer_type it doesn't recognize is
  literally the string `"Skipped"` — so a correctly-saved, non-skipped
  file-upload answer showed as "Skipped" everywhere `display_name` is used
  (the response's Answers tab, most visibly) even though `skipped=False` and
  `value_file_upload` were populated correctly the whole time. This was
  reported as "the answer got skipped" and took a full automated-browser
  reproduction (locally and against a live deployment, matching the exact
  reported layout/question mix) to rule out an actual save-path bug before
  finding the real (much smaller) cause. Moral: if a `file_upload`-specific
  symptom shows up, check whether it's actually a *display* computation
  (`_compute_display_name`, `file_upload_links`) before assuming the
  save/validate path broke — those two are well-tested; the display layer is
  exactly the kind of thing easy to forget when adding a new answer_type.

- **There are THREE separate per-question-type dispatch chains on the
  frontend, not two.** It's easy to think "live taking flow"
  (`survey.question_container`) and "results page"
  (`survey.survey_page_statistics_question`) are the whole surface, since
  those are the two this module hooked from day one. There's a third:
  **`survey.survey_page_print`** (`survey/views/survey_templates_print.xml`)
  — the respondent-facing "Review your answers" page (reached from the
  Thank You screen's own "Review your answers" button) — which is its own
  template with its own closed per-type `t-if` chain, entirely independent
  of `question_container`. Missing this one meant uploaded files saved and
  validated correctly, showed correctly on the *results* page, and even
  showed correctly *during* the taking flow — but the question title
  rendered with nothing underneath on the review page specifically (found
  via a real screenshot, not a guess). Fixed by
  `views/survey_templates_print.xml`. **If you add another new question
  type here later, or to any sibling survey module, hook all three
  templates, not just `question_container`.**

## Quick map: "I want to change X, where do I look?"

| Change | File |
|---|---|
| Max size / multiple-file config fields | `models/survey_question.py` |
| Answer storage (attachment link) | `models/survey_user_input.py` — `value_file_upload` on `SurveyUserInputLine` |
| Save-on-submit dispatch | `models/survey_user_input.py` — `SurveyUserInput._save_lines` / `_get_line_answer_values` |
| Upload/delete endpoints, size/count/token validation | `controllers/main.py` |
| Backend question-builder UI (Options tab fields, preview block) | `views/survey_question_views.xml` |
| Taking-form markup (dropzone, file chips, hidden value input) | `views/survey_templates.xml` — `question_file_upload` |
| Results-page display (download links per respondent) | `views/survey_templates_statistics.xml` — `question_result_file_upload` |
| Respondent's own "Review your answers" page display | `views/survey_templates_print.xml` |
| Upload/remove AJAX behavior | `static/src/interactions/survey_file_upload.js` |
| Folding the file answer into core's submit/validate switches | `static/src/interactions/survey_form_patch.js` |
| Styling | `static/src/scss/survey_file_upload.scss` |

## Conventions used in this codebase

- Field/route naming is prefixed `file_upload_` / `/survey/file_upload/...`
  for clarity — no company-specific prefix, since this inherits core `survey`
  models directly and there's no collision risk to guard against.
- Python: standard Odoo ORM conventions; overrides check their own
  type/answer_type first and delegate to `super()` otherwise, rather than
  reimplementing the base dispatch chains.
- JS: one `Interaction` per concern (`survey_file_upload.js` for the widget
  itself, `survey_form_patch.js` for extending the stock form) rather than
  cramming both into a patch of the core file.

## Known v1 limitations (see CHANGELOG.md)

No drag-and-drop (click-to-browse only), no results-page pagination for this
answer type, no admin bulk-download. None of these affect correctness of the
core feature — pick them up if/when actually requested.

## When you're done with a change

Update `CHANGELOG.md` (Keep a Changelog format), bump the version in
`__manifest__.py` (Odoo format: `19.0.{major}.{minor}.{patch}`), and if you
changed one of the non-obvious decisions above, update this file so the next
AI session (or the next developer) doesn't have to rediscover it.
