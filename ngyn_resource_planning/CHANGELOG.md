# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}.{build}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

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
