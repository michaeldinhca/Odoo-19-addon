# Survey Theme

A pure front-end restyle of Odoo Survey's respondent-facing taking flow —
start screen, every question type, progress bar/navigation, completion
screen. No behavior changes; works with every `questions_layout` setting
(one page, one section per page, one question per page).

![status](https://img.shields.io/badge/status-v2-orange)
![odoo](https://img.shields.io/badge/Odoo-19.0%20Community-714B67)
![license](https://img.shields.io/badge/license-LGPL--3.0-blue)

Built from a mobile-first mockup reviewed and approved by the user before
any real code was written — see [`CLAUDE.md`](CLAUDE.md) for the design
rationale and the long-text-option bug it specifically fixes.

## Features (v2.0.0)

- **Per-survey "Use Survey Theme" toggle** (Options tab) — each survey
  independently chooses this restyled look or the stock Odoo appearance.
  Defaults on; a survey with it off renders genuinely stock styling, not
  an approximation.
- **Company logo** on the survey taking page header.
- **Accent color / shape language** — indigo accent, rounded shapes,
  applied to buttons (including the final "Submit" CTA), the progress bar,
  and the selection ring.
- **Fixes long answer-option text wrapping badly** against the selection
  icon on simple/multiple-choice questions — pure CSS fix (`display: flex`
  on the option label), no template or JS changes. Reproduced against a
  theme-off survey to confirm this is a real stock-Odoo issue this module
  fixes, not something it introduced.
- Wider option spacing, a card treatment per question, pill-shaped nav
  buttons, horizontal-scroll matrix fallback with matching header color.

## Requirements

- Odoo **19.0 Community** (or Enterprise — no Enterprise-only APIs used).
- Standard app: `survey` (declared as a dependency, installed automatically).
- Pairs well with `survey_file_upload` (same repo) — both target the
  `survey.survey_assets` bundle, so the file-upload widget picks up this
  theme's accent color/shape automatically when both are installed.

## Installation

1. Copy (or `git clone`) this repository's `survey_theme/` folder into your
   Odoo `addons` path.
2. Restart the Odoo server, or enable Developer Mode and go to
   **Apps → Update Apps List**.
3. Search for **Survey Theme** and click **Install**.
4. Set your company logo under **Settings → General Settings → Companies**
   if it isn't already set — that's what renders on the survey header.
5. Every survey defaults to using the theme. To opt a specific survey out
   (stock Odoo look), open it → **Options** tab → uncheck **Use Survey
   Theme**.

## License

LGPL-3.0 — see [`LICENSE`](LICENSE).

## Author

NGYN Solutions Inc. — https://ngynsolutions.com
