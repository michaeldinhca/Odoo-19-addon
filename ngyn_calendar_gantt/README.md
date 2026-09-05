# NGYN Calendar Timeline

A read-only Gantt-style weekly timeline for Odoo's Calendar app.

## Why

Odoo Community's Calendar has no Gantt/timeline view (that widget is Odoo
Enterprise-only). When several bookings land in the same time slot, the
day/week calendar grid gets cramped, and there's no way to see who — or which
CRM opportunity — is already busy.

## What it does

- Adds a **Timeline** menu item next to **Calendar** in the Calendar app.
- Rows are grouped by either the native `opportunity_id` (CRM Opportunity) or
  a new `x_ngyn_installer_ids` many2many field this module adds to
  `calendar.event` (Installers — plain Contacts). Pick which one under
  **Calendar > Configuration > Settings > Calendar Timeline**.
- Overlapping bookings within a row are stacked into separate lanes instead
  of being drawn on top of each other.
- Clicking a bar opens the underlying event.

v1 is intentionally read-only — no drag-to-reschedule yet.

## License and Enterprise-code policy

Licensed LGPL-3 (see `LICENSE`). This module is built entirely from scratch
against Community's own `web`/`calendar`/`crm` addons (all LGPL-3). It does
not use, depend on, vendor, or derive from Odoo Enterprise's `web_gantt` (or
any other Enterprise-only module) — deliberately, per explicit instruction.
If you ever see Enterprise gantt-specific view types, arch attributes, or JS
imports creeping into this module, that's a bug: revert it.

## Configuration

`ir.config_parameter` key `ngyn_calendar_gantt.groupby_field`, one of:
- `opportunity_id` (default)
- `x_ngyn_installer_ids`

Set via the Settings UI, not by hand, in normal use.
