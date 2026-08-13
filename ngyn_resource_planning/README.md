# NGYN Resource Planning

A dense, multi-project **weekly resource planning workspace** for Odoo 19 Enterprise,
built on top of the standard Project, HR, and Timesheets apps.

Pin several projects at once, plan hours per task/team member down to the quarter
hour, and see everyone's weekly load — across *every* project they're on, not just
the ones you're currently editing — against a configurable planning buffer.

This is not a replacement for the Planning app. It's a purpose-built overview layer
for staffing decisions across a large portfolio (originally built for a ~20-person
engineering firm running ~100 concurrent projects), where the standard Project/
Planning UI is too granular per-project and not dense enough across projects.

![status](https://img.shields.io/badge/status-v1%20first%20install-orange)
![odoo](https://img.shields.io/badge/Odoo-19.0%20Enterprise-714B67)
![license](https://img.shields.io/badge/license-LGPL--3.0-blue)

---

## Features (v1.0.0)

- **Left pane** — searchable, filterable, sortable project list with live health
  status (On track / Stalled / Over burn), computed from time elapsed vs. hours
  logged against charged hours.
- **Right pane** — pin several projects at once into a planning workspace. Each
  project's tasks and assigned team members lay out as a weekly grid, editable
  down to 0.25h. Past weeks lock automatically and show actual logged hours from
  Timesheets instead of the plan.
- **Weekly load strip** — every team member's total scheduled hours per week,
  across all projects, against a 70%-style planning buffer and a hard capacity
  cap. Searchable, filterable by role, and pinnable to a working shortlist.
- **Role-filtered "add team member" picker** instead of a long flat dropdown.
- **Week navigator** — pages a 14-week visible window forward/back over a stable,
  continuous week timeline; a "Today" button jumps back to the current week.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how it's built and
[`docs/ROADMAP.md`](docs/ROADMAP.md) for what's intentionally deferred past v1.

## Requirements

- Odoo **19.0 Enterprise** (built and tested for; not verified against Community —
  see [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the Enterprise-specific
  assumption).
- Standard apps: `project`, `hr`, `hr_timesheet` (all declared as dependencies in
  the manifest and installed automatically).

## Installation

1. Copy (or `git clone`) this repository's `ngyn_resource_planning/` folder into
   your Odoo `addons` path.
2. Restart the Odoo server, or if already running, enable Developer Mode and go to
   **Apps → Update Apps List**.
3. Search for **NGYN Resource Planning** and click **Install**.
4. A **Resource Planning** menu appears at the top level.

## Configuration

Before the workspace shows meaningful numbers:

1. **Charged hours** — open a task, set **Charged Hours** in the new *Resource
   Planning* section of the task form. This is the budget the workspace plans
   against.
2. **Weekly buffer / hard capacity** — open an employee record, set **Weekly
   Planning Buffer (h)** and **Weekly Hard Capacity (h)** in the new *Resource
   Planning* section. Defaults to 28h / 40h (a 70% buffer on a standard week) if
   left unset.
3. Open **Resource Planning → Weekly Plan**, pin a project, and start assigning
   team members to tasks.

## Repository layout

```
.
├── ngyn_resource_planning/     # the actual Odoo module — copy this into addons
├── docs/
│   ├── ARCHITECTURE.md         # how the OWL client action & data flow work
│   ├── DATA_MODEL.md           # every model/field this module adds, and why
│   ├── DEVELOPMENT.md          # local setup, where to make changes, testing gaps
│   └── ROADMAP.md              # known v1 limitations and the planned next phases
├── CLAUDE.md                   # context file for AI coding assistants (see below)
├── CHANGELOG.md
├── LICENSE
└── README.md                   # you are here
```

## Working on this with an AI coding assistant

[`CLAUDE.md`](CLAUDE.md) at the repo root is written for tools like Claude Code
(and works fine as context for other AI coding assistants too) — it explains what
this module does, the non-obvious design decisions, where things live, and what
the next steps are, so a fresh AI session can pick up the work without re-deriving
context from scratch.

## License

LGPL-3.0 — see [`LICENSE`](LICENSE).

## Author

NGYN Solutions — https://www.ngynsolutions.com
