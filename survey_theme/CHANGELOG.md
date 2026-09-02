# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

## [2.1.0] - 2026-09-02

### Changed
- **`survey.use_custom_theme` (Boolean) replaced with `survey.theme_style`
  (Selection: `'none'` / `'indigo'`, default `'indigo'`)**, per request —
  more theme styles are planned, and a boolean can't grow into a picker.
  Existing surveys' on/off state is preserved via
  `migrations/19.0.2.1.0/pre-migrate.py` (verified against a real upgraded
  database, not just a fresh install: a survey that had the toggle off came
  out as `theme_style='none'`, not silently reset to the new default).
- **`survey_theme.scss` split into two scopes**: `.o_survey_theme_custom`
  (shape/spacing/layout - the long-text choice-option fix, card treatment,
  button radius, matrix scroll - anything a *future* style should also get)
  and `.o_survey_theme_<style>` (that style's own colors, e.g.
  `.o_survey_theme_indigo`'s `$accent: #4F46E5`). Both classes are applied
  together whenever `theme_style != 'none'`. Adding a new style going
  forward is a new selection value + its own `.o_survey_theme_<value>`
  color block - no template change, no restructuring. See `CLAUDE.md`.
- Backend field now uses `widget="radio"` (matching `questions_layout` in
  the same view) instead of a checkbox, since it's a picker now, not a
  toggle.

## [2.0.1] - 2026-09-02

### Changed
- Module author/copyright attribution changed to NGYN Solutions Inc.
  (`https://ngynsolutions.com`), matching this repo's other original
  modules (e.g. `ngyn_resource_planning`) rather than an individual name.

## [2.0.0] - 2026-09-02

### Changed (breaking - internal architecture only, no data migration needed)
- **Reworked from a global Sass-variable override to a fully scoped restyle**,
  to support the new per-survey toggle below. `$primary`/`$border-radius` are
  compile-time Sass variables baked identically into every survey's compiled
  CSS - there is no way to make a variable override apply to only *some*
  surveys at runtime. Every rule in `survey_theme.scss` now lives under
  `.o_survey_theme_custom` (added to `.o_survey_wrap` - see `views/
  survey_templates.xml` - only when `survey.use_custom_theme` is set), and
  uses its own `$survey-theme-accent`/radius variables instead of touching
  Bootstrap's globals. A survey with the toggle off now gets genuinely 100%
  stock Odoo styling, not just "close to it."

### Added
- **Per-survey "Use Survey Theme" toggle** (`survey.use_custom_theme`,
  Options tab, next to `questions_layout`) - each survey independently
  chooses this restyled look or the stock Odoo appearance. Defaults to on.
- Themed `.btn-secondary` (the stock template's button for the *last*
  question, `button[value=finish]` - not a minor button, it's the actual
  submit CTA) and the matrix table header/row-label background, so nothing
  is left in stock Bootstrap tan/mauve next to an otherwise-themed page -
  caught during visual QA, not in the original design pass.

### Fixed (this release, on top of 1.0.0's original fix)
- **A subtle QWeb inheritance gotcha almost shipped a broken layout.** The
  first attempt at the per-survey class added a `t-attf-class` attribute to
  `.o_survey_wrap` alongside its existing static `class="wrap o_survey_wrap
  d-flex"` - assumed QWeb would merge the two. It doesn't: `t-attf-class`
  **replaces** the static `class` attribute outright when both are present
  on the same element, silently dropping `wrap`/`o_survey_wrap`/`d-flex`.
  Caught by inspecting the actual rendered HTML, not by assumption. See
  `CLAUDE.md` for the fix and why `t-att-class` + inheritance's `add=`
  mechanism was avoided too (real risk of feeding QWeb an invalid combined
  Python expression on `survey.layout`'s own dynamic background/shadow
  class logic).

### Known limitations (v1, unchanged from 1.0.0)
- Matrix questions get a horizontal-scroll fallback and a color touch-up,
  not the full stacked-card mobile layout explored in the design mockup.
- Backend survey builder and results/statistics pages are untouched by
  design - taking-flow only.

## [1.0.0] - 2026-09-02

Initial release (superseded by 2.0.0's architecture rework the same day,
before this ever shipped to the live deployment - see `CLAUDE.md`).

### Added
- Company logo on the survey taking page header.
- Sass variable override setting `$primary` (indigo accent) and the
  Bootstrap radius scale, applied globally.
- Card treatment per question, wider answer-option spacing, pill-shaped
  nav/submit buttons, horizontal-scroll safety net on matrix tables.

### Fixed
- Long answer-option text wrapping badly against the selection icon,
  fixed via `display: flex` on `.o_survey_choice_btn` (floats are ignored
  on flex items per the CSS spec) - unchanged in 2.0.0, just now scoped.
