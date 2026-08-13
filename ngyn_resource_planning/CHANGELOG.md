# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}.{build}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

## [1.0.1] - 2026-08-13

Post-release fixes found during code review, before this version had been
installed against a live database.

### Fixed
- `loadData()` called `this.orm.readGroup(...)`, which does not exist in this
  Odoo 19 build (renamed to `webReadGroup`, with a different argument order
  and result shape — `{ groups, length }` instead of a plain array, and
  aggregate values keyed by the full spec string e.g. `"unit_amount:sum"`).
  This crashed the dashboard on open for any database with at least one
  active project.
- `_sql_constraints` (the old list-of-tuples model attribute) is silently
  no longer read by this Odoo 19 build's ORM — both uniqueness constraints on
  `ngyn.task.assignment`/`ngyn.task.assignment.week` were not actually
  enforced. Converted to the `models.Constraint(sql, message)` class-attribute
  form.
- Date-only strings from the server (`week_start_date`, timesheet `date`,
  project `date_start`/`date`) were parsed with `new Date(str)`, which the JS
  spec parses as UTC midnight; converting that back with local-time getters
  (as `mondayOf()`/`toLocaleDateString()` do) landed on the wrong calendar day
  outside a narrow range of timezones — shifting planned/actual hours into the
  wrong week column and shifting displayed project dates by a day. Added
  `parseDateOnly()`/reworked `toIso()` to stay in local time throughout.

## [1.0.0] - 2026-08-13

Initial release. First installable version, built from an interactive HTML mockup
(iterated over ~10 rounds of feedback — see `docs/ARCHITECTURE.md` for the design
history) and ported to a real Odoo 19 OWL client action backed by live ORM data.

### Added
- `ngyn.task.assignment` and `ngyn.task.assignment.week` models — the core data
  model for "who is on this task, how many hours, placed into which weeks."
- `project.task.x_ngyn_charged_hours` field (+ form view section).
- `hr.employee.x_ngyn_weekly_target_hours` / `x_ngyn_weekly_hard_hours` fields
  (+ form view section).
- `Resource Planning → Weekly Plan` menu and OWL client action:
  - Left pane: search, health filter chips (with live counts), sort, per-project
    mini stat block (Due / Charged / Allocated / Unscheduled).
  - Right pane: multi-project pinning, collapsible project & task rows, single-row
    compact project header, editable weekly hour grid (0.25h rounding), past-week
    lock with actual logged hours from Timesheets, role-filtered add-team-member
    picker.
  - Weekly load strip: per-employee per-week totals across all projects, buffer/
    hard-capacity tiering, search, role filter, shared pin-to-filter toggle
    (same icon/state used in the planning grid).
  - Week navigator: 14-week paged window over a stable week-index timeline, with
    a "Today" quick-jump.
- Basic access rights (`base.group_user`, full CRUD) for the two new models —
  **intentionally permissive for v1**, see `docs/ROADMAP.md`.

### Known limitations (see `docs/ROADMAP.md` for detail)
- No automated tests yet.
- Left pane loads up to 300 projects in one request; no server-side pagination.
- Access rights not yet role-differentiated (PM vs. task assignee vs. read-only).
- Hover explanations use native `title` tooltips rather than a styled popover.
- No horizontal-scroll-sync between the planning grid and the weekly load table
  (column widths are aligned via fixed table layout, which covers the important
  case; true scroll-sync was cut from v1 scope).

[1.0.0]: https://github.com/REPLACE_WITH_ORG/ngyn-resource-planning/releases/tag/v1.0.0
