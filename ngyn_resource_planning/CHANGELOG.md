# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The module itself is versioned using Odoo's convention: `{odoo_series}.{major}.{minor}.{patch}.{build}`
(e.g. `19.0.1.0.0`); this file's version headings use the trailing `major.minor.patch` for readability.

## [1.0.3] - 2026-08-13

### Fixed
- `resource_planning.scss`'s `.o_ngyn_rp_workspace` rule used
  `grid-template-columns: min(360px, 26vw) 1fr;` — a real, reproduced bug in
  this Odoo build's SCSS compiler (`libsass==0.22.0`, pinned by Odoo's own
  `requirements.txt`): it tries to evaluate a literal CSS `min()`/`max()` as
  Sass arithmetic instead of passing it through untouched, and errors on
  mixing `px` and `vw` units (`Internal Error: Incompatible units: 'vw' and
  'px'.`). This broke asset-bundle compilation for `web.assets_web` and
  `web.assets_web_print` **database-wide**, not just this module's own page
  — any database with this module installed would see a global
  "Style error. The style compilation failed." banner. Present since 1.0.0;
  only surfaced once a full asset rebuild was forced (earlier bundle caches
  had been serving pre-existing compiled CSS). Fixed by wrapping the whole
  expression in a string interpolation (`#{"min(360px, 26vw)"}`), the
  documented libsass workaround to force literal passthrough — confirmed via
  a direct `python3 -c "import sass; sass.compile(...)"` repro of the exact
  error, then verified fixed by compiling `web.assets_backend`,
  `web.assets_web`, and `web.assets_web_print` directly against the same
  module combination as `staging_20Jul` (all `ova_*` modules +
  `ngyn_resource_planning`, 127 modules total).

## [1.0.2] - 2026-08-13

Aligned the Odoo port with the original interactive HTML/JS mockup after a
direct feature-parity audit found several explanatory-UI pieces that never
made it into v1 (the mockup itself is not in this repo — see `CLAUDE.md`).
Business-rule formulas (health status, buffer tiers, allocation math) were
verified identical between mockup and port before this pass — this is UI
parity only, no calculation changes.

### Added
- Hover tooltips on weekly-load-strip cells (current and past/actual),
  matching the mockup's per-cell breakdown (`Xh allocated this week, of a
  Yh/wk buffer target (Zh hard capacity)...`).
- Hover tooltips on the project-card header stats (Charged / Allocated /
  Left to assign / Unscheduled), explaining what each number means.
- "Projects" pane header with a live, filter-aware count in the left pane.
- An explanatory row in the weekly load table when a search/role/pin filter
  matches no one, instead of silently rendering nothing.
- `title` on the weekly-load-strip's pin button (its twin in the planning
  grid already had one — was a real inconsistency, not intentional).
- A `max-width: 980px` responsive breakpoint stacking the two-pane layout
  into one column, matching the mockup.
- Restored the footnote's "Hover a cell for exact numbers" line, now that
  it's true again.

### Known still-deferred (per `ROADMAP.md`, not part of this pass)
- Styled tooltip popovers remain native `title`/`t-att-title` attributes,
  not the mockup's custom-positioned popover.
- No horizontal scroll-sync across the planning grids and the weekly load
  strip.

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
