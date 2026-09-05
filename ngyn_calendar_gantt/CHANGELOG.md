# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

## [1.1.0] - 2026-09-05

### Added
- Toolbar: a text search box (filters visible rows/bars by event, opportunity,
  or installer name — client-side against the currently loaded week, no
  server round-trip) and a live Group By picker (Opportunity/Installer)
  that reads/writes the same `ir.config_parameter` as the Settings screen,
  so switching no longer requires leaving the view.
- Timezone label in the header (`Intl.DateTimeFormat().resolvedOptions().timeZone`).
- Time axis is now scaled to business hours (6am–8pm) instead of a full
  24h day per column, with hour tick marks (6a/9a/12p/3p/6p) under each
  day header — makes bar positions actually readable instead of every
  event being squeezed into a sliver of a 24h-wide column. An event
  outside that window, or spanning past midnight, is visually clamped to
  the nearest edge rather than hidden or breaking the layout.
- Small avatar-initial chips on each bar when grouped by Opportunity,
  showing which installer(s) are on that booking (up to 2, +N overflow).
  Not shown when grouped by Installer, since the row itself already is
  the installer.
- Clicking a bar now opens the event in a modal form dialog
  (`@web/views/view_dialogs/form_view_dialog`, the same reusable
  Community core dialog used elsewhere in Odoo) instead of navigating
  away to a full-page form — closer to the normal Calendar app's
  click-to-edit feel. Saving refreshes the timeline in place.
- Row labels now wrap to multiple lines instead of truncating with an
  ellipsis, so the full opportunity/installer name is always visible.

### Known follow-ups (not in this pass, deliberately deferred)
- Drag-to-resize / drag-to-move (rescheduling directly on the timeline) —
  real interactive write-back, wants its own focused pass and testing.
- Month zoom level (only Week exists today).

## [1.0.0] - 2026-09-04

### Added
- Initial release: read-only weekly Gantt-style timeline for `calendar.event`,
  built as a standalone OWL client action (no Odoo Enterprise dependency).
- Rows grouped by `opportunity_id` (CRM) or new `x_ngyn_installer_ids`
  (Installers, Many2many to `res.partner`), selectable in
  Calendar > Configuration > Settings.
- Overlapping events within a row are packed into separate lanes.
- Click a bar to open the event form.
