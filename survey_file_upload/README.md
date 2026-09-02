# Survey File Upload

Adds a genuinely new **File Upload** question type to Odoo's Survey app, so
respondents can attach one or more files as their answer — something the stock
Survey app has no native equivalent for.

![status](https://img.shields.io/badge/status-v1-orange)
![odoo](https://img.shields.io/badge/Odoo-19.0%20Community-714B67)
![license](https://img.shields.io/badge/license-LGPL--3.0-blue)

This module was built from scratch against Odoo 19's actual survey internals
(jsonrpc submit route, the `Interaction` frontend framework, string-expression
view attributes) — it is not a port of any third-party module. See
[`CLAUDE.md`](CLAUDE.md) for why, and for the extension points a paid v16
third-party module (checked only for feature-scope reference, never for code)
doesn't share with v19.

## Features (v1.0.0)

- New **File Upload** question type, selectable in the question type radio
  group alongside the stock types.
- Per-question **maximum file size (MB)** and **allow multiple files** toggle,
  configured on the question's Options tab.
- **Non-blocking (AJAX) upload** — files are sent to the server and attached to
  the response as soon as they're picked, independent of the page-submit flow.
  Respondents can remove an uploaded file before moving on.
- Respects the existing **Mandatory Answer** constraint like every other
  question type — no separate "required" setting to configure.
- Uploaded files are listed with download links on the results page, per
  respondent.
- Attachments are cleaned up automatically when an answer is replaced or a
  response/line is deleted — no orphaned files left behind in the filestore.

## Requirements

- Odoo **19.0 Community** (or Enterprise — no Enterprise-only APIs are used).
- Standard app: `survey` (declared as a dependency, installed automatically).

## Installation

1. Copy (or `git clone`) this repository's `survey_file_upload/` folder into
   your Odoo `addons` path.
2. Restart the Odoo server, or if already running, enable Developer Mode and go
   to **Apps → Update Apps List**.
3. Search for **Survey File Upload** and click **Install**.

## Configuration

1. Open a survey, add a question, and set its **Question Type** to
   **File Upload**.
2. On the **Options** tab, set **Max File Size (MB)** (default 10) and toggle
   **Allow Multiple Files** if respondents may attach more than one file.
3. Set **Mandatory Answer** (Constraints group) if the question must be
   answered before the respondent can continue — this is the same field every
   other question type already uses.

## Repository layout

```
.
├── survey_file_upload/     # the actual Odoo module — copy this into addons
├── CLAUDE.md                # context file for AI coding assistants (see below)
├── CHANGELOG.md
├── LICENSE
└── README.md                # you are here
```

## Working on this with an AI coding assistant

[`CLAUDE.md`](CLAUDE.md) explains what this module does, the non-obvious design
decisions (particularly around the v19 API this was built against), where
things live, and known v1 limitations — so a fresh AI session can pick up work
here without re-deriving context from scratch.

## License

LGPL-3.0 — see [`LICENSE`](LICENSE).

## Author

Michael Dinh
