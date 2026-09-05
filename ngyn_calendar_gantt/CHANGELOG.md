# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

## [1.0.0] - 2026-09-04

### Added
- Initial release: read-only weekly Gantt-style timeline for `calendar.event`,
  built as a standalone OWL client action (no Odoo Enterprise dependency).
- Rows grouped by `opportunity_id` (CRM) or new `x_ngyn_installer_ids`
  (Installers, Many2many to `res.partner`), selectable in
  Calendar > Configuration > Settings.
- Overlapping events within a row are packed into separate lanes.
- Click a bar to open the event form.
