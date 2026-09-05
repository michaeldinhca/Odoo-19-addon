# NGYN Calendar Timeline

A Gantt-style weekly timeline for Odoo's Calendar app.

## Why

Odoo Community's Calendar has no Gantt/timeline view (that widget is Odoo
Enterprise-only). When several bookings land in the same time slot, the
day/week calendar grid gets cramped, and there's no way to see who — or which
CRM opportunity — is already busy.

## What it does

- Adds a **Timeline** menu item next to **Calendar** in the Calendar app.
- A real Odoo search bar (Filters / Group By / Favorites), backed by this
  module's own `views/calendar_event_search_views.xml` — Group By Opportunity
  (native `opportunity_id`) or Attendee (native `partner_ids`) out of the box.
  Add more filters/group-bys later by editing that XML file — no code change
  needed.
- Overlapping bookings within a row are stacked into separate lanes instead
  of being drawn on top of each other.
- Time axis is scaled to business hours (6am–8pm) with hour tick marks.
- Clicking a bar opens the event in a popup editor; drag its left/right edge
  to reschedule its start/end time directly on the timeline (snapped to 15
  minutes, clamped within that day).
- When grouped by Opportunity, a small icon on each row opens that CRM
  record in a lightweight popup (own minimal form, no chatter panel).
- A **New** button creates a fresh event from the timeline.

## License and Enterprise-code policy

Licensed LGPL-3 (see `LICENSE`). This module is built entirely from scratch
against Community's own `web`/`calendar`/`crm` addons (all LGPL-3). It does
not use, depend on, vendor, or derive from Odoo Enterprise's `web_gantt` (or
any other Enterprise-only module) — deliberately, per explicit instruction.
If you ever see Enterprise gantt-specific view types, arch attributes, or JS
imports creeping into this module, that's a bug: revert it.

## Adding a filter or Group By option

Edit `views/calendar_event_search_views.xml` — it's a plain Odoo `<search>`
view. A new `<filter string="..." name="..." context="{'group_by': '...'}"/>`
inside the `Group By` group adds a new grouping option; the Timeline picks up
whatever field the search bar's Group By menu has active (falls back to
Opportunity if none, or a field this module doesn't know how to render rows
for — currently only `opportunity_id` and `partner_ids` are supported row
dimensions; extending that list is a one-line change in
`static/src/js/calendar_gantt_action.js`'s `GROUPBY_FIELDS` map, matching
whatever new field name the XML filter groups by).
