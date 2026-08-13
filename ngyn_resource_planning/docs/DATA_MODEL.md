# Data model

## New models

### `ngyn.task.assignment`
One row per **(task, employee)** pair — "this person is on this task, for this
many total hours."

| Field | Type | Notes |
|---|---|---|
| `task_id` | Many2one → `project.task` | required, `ondelete='cascade'` |
| `project_id` | Many2one → `project.project` | related/stored from `task_id.project_id`, for fast filtering |
| `employee_id` | Many2one → `hr.employee` | required, `ondelete='cascade'` |
| `alloc_hours` | Float | total hours given to this person on this task |
| `week_line_ids` | One2many → `ngyn.task.assignment.week` | the weekly breakdown |
| `scheduled_hours` | Float, computed, stored | `Σ week_line_ids.hours` |
| `unscheduled_hours` | Float, computed, stored | `alloc_hours - scheduled_hours` |

SQL constraint: one row per `(task_id, employee_id)` — a person can't be
assigned to the same task twice; adjust `alloc_hours` on the existing row
instead.

### `ngyn.task.assignment.week`
One row per **(assignment, week)** — a single editable cell in the planning
grid.

| Field | Type | Notes |
|---|---|---|
| `assignment_id` | Many2one → `ngyn.task.assignment` | required, `ondelete='cascade'` |
| `week_start_date` | Date | **always a Monday** — see `docs/ARCHITECTURE.md` §"Week timeline" |
| `hours` | Float | the hour value shown in that grid cell |

SQL constraint: one row per `(assignment_id, week_start_date)`.

A row is **created** on first non-zero entry for a cell, **updated** on
subsequent edits, and **deleted** (not zeroed) when the user clears a cell back
to 0 — see `onWeekChange()` in the JS. This keeps the table free of zero-value
noise and makes "does this person have any plan for this week at all" a simple
existence check.

## Extended standard models

### `project.task` (+2 fields)
| Field | Type | Purpose |
|---|---|---|
| `x_ngyn_charged_hours` | Float | Hours sold/charged to the client for this task — the budget the workspace plans against. Shown on the task form under a new "Resource Planning" group, before the notebook tabs. |
| `x_ngyn_assignment_ids` | One2many → `ngyn.task.assignment` | reverse relation, not currently shown on any view — available for future use (e.g. a smart button showing assignment count). |

### `hr.employee` (+2 fields)
| Field | Type | Default | Purpose |
|---|---|---|---|
| `x_ngyn_weekly_target_hours` | Float | 28.0 | The "70% buffer" planning target per week. Configurable per person/role since some roles (PM, principal) sustain a lower percentage due to admin/meeting load. |
| `x_ngyn_weekly_hard_hours` | Float | 40.0 | Full weekly capacity. Scheduling past this is flagged red in the weekly load strip. |

## Models read but never written by this module

- **`project.project`** — `name`, `partner_id`, `date_start`, `date` (the
  Enterprise "Expiration Date"/deadline field). If these dates are unset for a
  project, health status can't be computed (see `docs/ARCHITECTURE.md`).
- **`account.analytic.line`** (Timesheets) — `task_id`, `employee_id`, `date`,
  `unit_amount`. Used two ways:
  1. Bucketed into week-index buckets client-side to show "actual hours" on
     locked past-week cells (per task, per employee).
  2. Summed per-project (regardless of task) via `readGroup` for the project-
     level "% logged" health metric — this is intentionally broader than the
     per-task actuals, since some logged time may not be tied to a specific
     task.
- **`hr.employee`** for the base fields (`name`, `job_title`) used to display
  role — `job_title` is a free-text field on the standard employee form, not
  the `hr.job` model. If your database uses structured job positions instead
  of free text, `job_title` may be empty; see `docs/ROADMAP.md`.

## Entity relationship (text diagram)

```
project.project 1───* project.task 1───* ngyn.task.assignment *───1 hr.employee
                                              │
                                              │ 1
                                              │
                                              *
                              ngyn.task.assignment.week

project.task, project.project ···(read-only)··· account.analytic.line ···(read-only)··· hr.employee
```
