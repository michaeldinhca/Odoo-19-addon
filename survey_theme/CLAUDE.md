# CLAUDE.md — context for AI coding assistants

Read this first. It's written so a fresh AI session can understand what
this module is, why it's built the way it is, and what to do next — without
re-deriving context from the code alone.

## What this is

An Odoo 19 Community addon (`survey_theme`) that restyles the Survey app's
respondent-facing taking flow — start screen, every question type, progress
bar/navigation, completion screen. **Per-survey opt-in/out**
(`survey.use_custom_theme`, default on) — a survey with the toggle off
renders genuinely stock Odoo styling, not an approximation of it.

## How it got here

Built from a mobile-first mockup (a multi-artboard Claude Design canvas)
that the user reviewed and iterated on *before* any real module code was
written — colors, spacing, and the long-text fix below were all settled in
that mockup first. If you're asked to change the look, consider whether
there's an updated mockup to work from rather than guessing.

## Non-obvious things worth knowing before you touch the code

- **Everything is scoped under `.o_survey_theme_custom` — this is not
  optional/cosmetic, it's the whole point of the per-survey toggle.** An
  earlier version of this module set `$primary`/`$border-radius` via a
  prepended Sass variable file (the same technique Odoo's own website theme
  picker uses). That works great for a global reskin, but **cannot** support
  a per-survey runtime toggle: Sass variables are compile-time, baked
  identically into every survey's CSS output — there's no way to make that
  override apply to only *some* surveys. When the toggle requirement showed
  up, the whole approach was reworked: `survey_theme.scss` now defines its
  own `$survey-theme-accent`/radius variables (never touching Bootstrap's
  globals) and wraps every rule in `.o_survey_theme_custom`, which
  `views/survey_templates.xml` adds to `.o_survey_wrap` conditionally on
  `survey.use_custom_theme`. **If you're asked to add a new visual rule,
  it must go inside that `.o_survey_theme_custom { ... }` block** — a rule
  added outside it applies to every survey regardless of the toggle, which
  defeats the entire feature.

- **`t-attf-class` REPLACES a static `class` attribute on the same element
  — it does not merge with it.** The per-survey class is added via:
  ```xml
  <xpath expr="//div[hasclass('o_survey_wrap')]" position="attributes">
      <attribute name="t-attf-class"> #{'o_survey_theme_custom' if survey and survey.use_custom_theme else ''}</attribute>
  </xpath>
  ```
  targeting `survey.survey_page_fill`'s `<div class="wrap o_survey_wrap
  d-flex">`. The first attempt assumed QWeb would merge a new
  `t-attf-class` with the existing static `class` attribute (a pattern that
  *does* work in plenty of other Odoo views). It doesn't here — verified by
  fetching the actual rendered HTML, not by assumption — the compiled
  output was `<div class=" o_survey_theme_custom">`, having silently
  dropped `wrap`, `o_survey_wrap`, and `d-flex` entirely. Also deliberately
  **not** using XML inheritance's `<attribute name="t-att-class" add="..."
  separator=" ">` mechanism on `survey.layout`'s own `wrapwrap` div (which
  already has a `t-att-class` with a big Python ternary expression for the
  background-image/shadow logic) — string-concatenating a second Python
  expression fragment onto that via `add=` is a real risk of producing
  invalid combined Python that breaks CORE survey rendering for every
  installation, themed or not. If you need to add another conditional class
  somewhere, prefer a plain `<div>` that doesn't already carry a static
  `class` (or replace the *whole* class value deliberately, keeping the
  original literal classes in the new `t-attf-class` string) over assuming
  merge behavior.

- **After editing `survey_theme.scss`, a *running* dev server may keep
  serving a stale compiled bundle even after `-u survey_theme`.** Module
  upgrade reloads Python/views immediately, but the compiled
  `survey.survey_assets.min.css` is a separately cached `ir.attachment`,
  content-hash-keyed — and in local testing this genuinely did NOT
  auto-invalidate on the next request from an already-running server (the
  `/web/assets/debug/...` route recompiled fresh and looked correct while
  the real page kept serving the old `.min.css`). If a restyle "isn't
  showing up" after a change + upgrade despite the CSS being correct on
  disk, delete the stale bundle attachments and let them regenerate:
  ```python
  env['ir.attachment'].sudo().search([('name', 'like', 'survey.survey_assets%')]).unlink()
  env.cr.commit()
  ```
  Don't assume the restyle is broken from a screenshot alone until you've
  ruled this out — it cost real debugging time here before the actual fix
  (below) was found underneath it.

- **The long-text option bug, and why the fix is a few lines of CSS.** The
  original bug report: real answer options with long labels (e.g.
  *"Wholesale — I'm a contractor, reseller, or sign shop"*, pulled from a
  real reference form during design review) wrapped badly against the
  selection icon. Root cause: `.o_survey_choice_btn` (the visible label
  wrapping each option — the actual `<input>` is `invisible
  position-absolute`) lays out its children — an optional keyboard-shortcut
  badge, a check/circle-thin FontAwesome icon, then the label text — using
  Bootstrap `float-start`/`float-end` in the stock template
  (`survey/views/survey_templates.xml`, `question_simple_choice` /
  `question_multiple_choice`). Floats work fine for short one-line labels,
  but text wraps *around* a float rather than flowing beside it once a
  label runs 2-3 lines — reproduced directly against a **theme-off** survey
  during QA (stock styling, same broken wrap) to confirm this is a real
  stock-Odoo issue, not something this module could have introduced.
  **The fix**: `.o_survey_theme_custom .o_survey_choice_btn { display: flex;
  align-items: flex-start; }`. Per the CSS spec, **float does not apply to
  flex items** — so this single declaration neutralizes every
  `float-start`/`float-end` on its children without touching the template,
  and the existing DOM order (badge → icon → text) already lays out
  left-to-right correctly once floats are out of the way. The
  `.o_survey_selected` class-toggle logic that shows/hides the check vs.
  empty-circle icon is untouched (it was never float-dependent — see
  `survey_templates_form.scss` lines ~147-152, a plain
  `&.o_survey_selected i.fa-circle-thin { display: none }` class rule).
  **Don't "fix" this by editing the choice/multiple-choice templates** —
  the CSS-only fix is deliberately lower-risk than a template override.

- **`.btn-secondary` needs theming too — it's not a minor button.** The
  stock `survey_page_fill` template swaps the submit button's class to
  `btn-secondary` specifically for the *last* question
  (`t-attf-class="btn #{'btn-secondary' if survey_last else 'btn-primary'}
  ..."`) — i.e. the actual "Submit"/"Get My Quote" CTA on a themed survey.
  Missing this in the first visual QA pass left the single most important
  button in stock Bootstrap tan next to an otherwise fully-themed page —
  caught by actually looking at screenshots of every screen, not by
  reasoning about the SCSS alone. Same story for the matrix table's
  `thead`/row-label background color.

- **Why the company logo goes in `survey.survey_fill_header`, not
  `survey.layout`.** That template is called exactly once per page load
  from `survey_page_fill`, **regardless of `questions_layout`** (one_page /
  page_per_section / page_per_question) and regardless of state (start /
  in_progress / done) — so it's the one place that reaches the whole taking
  flow without needing three separate overrides. Gated on both
  `survey.use_custom_theme` and `env.company.logo` — nothing renders (not
  even a broken-image box) for a theme-off survey or a company without a
  logo configured. Uses `/web/image/res.company/<id>/logo` (the standard
  Odoo company-logo image route).

- **Why `.js_question-wrapper` (not a new wrapper div) gets the card
  treatment.** That class already wraps every question — and the start/
  completion screens too — in every layout, including stacked repeatedly
  in `one_page` layout (one card per question, which reads fine). Styling
  the existing element instead of introducing a new wrapper avoids any
  template change for the card look itself.

- **Matrix questions deliberately don't get the full mobile stacked-card
  treatment from the mockup** — that needs a genuinely different DOM
  structure per row (a template-level change), out of scope for a "pure
  restyle" pass. What's here is a horizontal-scroll safety net plus a color
  touch-up (header/row-label background matches the accent) so it at least
  reads as part of the same theme.

## Quick map: "I want to change X, where do I look?"

| Change | File |
|---|---|
| The per-survey toggle field | `models/survey_survey.py` |
| Where the toggle shows in the backend | `views/survey_survey_views.xml` |
| Accent color, corner radius (local SCSS variables, not Bootstrap's) | `static/src/scss/survey_theme.scss`, top of file |
| Question card look, choice-option layout/spacing, progress bar, buttons, matrix colors/scroll | `static/src/scss/survey_theme.scss` |
| Company logo placement/sizing, the `.o_survey_theme_custom` class injection | `views/survey_templates.xml` |
| `survey_file_upload` widget theming (dropzone/button/chip/progress bar) | `static/src/scss/survey_theme.scss`, "File upload widget" section — these selectors just don't match if that module isn't installed |

## Known v1 limitations (see CHANGELOG.md)

Matrix questions get a horizontal-scroll fallback and a color touch-up, not
a full mobile stacked-card rebuild. Backend builder and results/statistics
pages are untouched by design.

## When you're done with a change

Update `CHANGELOG.md` (Keep a Changelog format), bump the version in
`__manifest__.py` (Odoo format: `19.0.{major}.{minor}.{patch}`), and if you
changed one of the non-obvious decisions above, update this file. If you
changed `survey_theme.scss` and are testing on an already-running dev
server, remember the stale-bundle gotcha above before concluding a visual
change "didn't work."
