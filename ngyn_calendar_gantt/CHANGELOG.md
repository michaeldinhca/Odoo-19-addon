# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

## [1.3.1] - 2026-09-08

### Fixed
- **Searching or filtering by Attendee while grouped by Attendee could show a
  matching booking under co-attendees who didn't personally match**, e.g.
  searching for one specific person on a multi-attendee event also created a
  row for everyone else on that same event, or a custom Filter based on a
  Contact tag (`partner_ids.category_id...`) showed every attendee of a
  matching booking, not just the tagged one. Root cause: a domain restricts
  which *events* qualify, not which specific attendee on a qualifying event
  the row-grouping should explode into — an inherent property of filtering
  and grouping by the same many2many field, not specific to how this module
  built it, but fixable here. `resolveFieldRestriction()` now inspects the
  active search domain for conditions on whichever field rows are currently
  grouped by and resolves them into a concrete set of ids (handling a direct
  id/id-list match, a relational condition like `partner_ids.category_id.name`
  via a lookup query, and the search bar's own free-text fallback via that
  model's real `name_search`) — row creation for a matching event is then
  restricted to just those ids. Deliberately conservative: bails to the
  previous show-every-co-attendee behavior whenever the domain has an
  explicit `|`/`!` anywhere, rather than risk an incorrect narrow guess under
  a boolean combination it can't safely reason about.

## [1.3.0] - 2026-09-07

### Added
- **Bars are now colored to match the event's own Tag** (`calendar.event.categ_ids`
  / `calendar.event.type.color`), using Odoo's own standard tag color palette
  (`$o-colors`) so a bar's color is exactly the same color shown on the
  Tags field on the real calendar record — no separate color scheme to learn.
  When an event has several tags, the first one wins (matches how most Odoo
  widgets lead with the first tag rather than blending colors). Text color
  (white vs. dark) is picked automatically per bar for readability against
  whichever tag color it got.
- **Events with no tag at all render as light grey with a diagonal stripe**,
  a deliberately distinct pattern (not just "grey," which could be mistaken
  for a real tag color) so "nobody has categorized this yet" reads as its
  own state at a glance.
- Tag name (when present) now appears in the bar's hover tooltip alongside
  the existing name/time/attendees.

## [1.2.1] - 2026-09-05

### Fixed
- **Two events that don't actually overlap could still render as visually
  overlapping bars** when close together (e.g. a 1-hour booking followed 15
  minutes later by another) — the minimum-render-width floor added in 1.1.0
  for legibility widened a short bar enough to visually collide with its
  neighbor, even though lane-packing had correctly kept them non-overlapping
  in time. Lane-packing now knows about that floor too: within a lane, each
  bar's rendered left edge is pushed to at least the previous bar's rendered
  right edge, so two bars in the same lane can never visually overlap
  regardless of how close their real times are. A bar's position only ever
  shifts *later* than its true start when a floored neighbor to its left
  demands it — never earlier, and never for bars in different lanes.
- **`OwlError: Invalid props for component 'ControlPanel': 'display' is not
  an object`**, thrown only in debug mode (Owl's strict prop validation only
  runs against non-minified/dev assets — reported directly from
  `odoo-comm-demo.ngynsolutions.com` with a debug-mode stack trace). Root
  cause: `Layout`'s own template forwards `props.display.controlPanel`
  itself as `ControlPanel`'s `display` prop (confirmed by reading
  `web/static/src/search/layout.xml`), not the whole `display` object — this
  module passed `display="{controlPanel: true}"`, i.e. a boolean, where an
  object was expected. Fixed to `display="{controlPanel: {}}"`. Harmless in
  production (prop validation is skipped there) but a real latent bug,
  worth fixing regardless of where it happened to surface first.

## [1.2.0] - 2026-09-05

### Changed
- **Replaced the hand-rolled search box + Group By `<select>` with Odoo's real
  search bar** (Filters / Group By / Favorites), via `WithSearch` + `Layout` +
  `SearchBar` (`@web/search/...`, Community/LGPL-3 — no new Odoo view type
  registration needed, no `ir.actions.act_window` conversion). New dedicated
  `views/calendar_event_search_views.xml` (`<search>` view, own id, not an
  inherit of calendar's stock search) — adding a filter or Group By option
  going forward is purely editing that XML file.
- **Removed the custom `x_ngyn_installer_ids` field** — its own "Select
  attendees…" picker already listed the exact same contacts. Grouping by
  "who" now uses the native `calendar.event.partner_ids` (Attendees) instead.
  A `migrations/19.0.1.2.0/pre-migrate.py` script copies any already-seeded
  installer assignments onto Attendees before the old field disappears (safe
  on a fresh install; no-ops if the old relation table never existed).
- Removed the now-redundant `res.config.settings` Group By picker and its
  Settings-screen entry — the real Group By menu replaces it, and "Save
  current search" → Favorites (with Default filter) is the native way to
  persist a preferred default.

### Added
- **Drag-to-resize**: dragging a bar's left/right edge reschedules the
  event's start/end time (15-minute snapping, clamped within that day's
  business-hours window), with a live floating label showing the new time
  and the delta (e.g. "12:00 PM (+2h)") while dragging.
- **CRM quick-view icon**: when grouped by Opportunity, a small icon on each
  row opens that opportunity in a lightweight popup — a fresh, minimal
  `crm.lead` form (`views/crm_lead_view_form_popup.xml`) with no chatter/
  log-note panel, not the full stock Opportunity form.
- **New button**: creates a fresh `calendar.event` from the Timeline,
  defaulting to 9am on the currently viewed day/week.

### Known follow-ups (not in this pass, deliberately deferred)
- Drag-to-*move* a whole bar to a different day/slot (only edge-resize is in
  this pass).
- Click-on-an-empty-cell to create a pre-filled event (the New button is a
  generic create for now).
- Month zoom level (only Week exists today).

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
