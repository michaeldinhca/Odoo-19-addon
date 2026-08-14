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

**Rows are no longer only created through the "+ Add team member" picker.**
`_ensure_assignments(pairs)` (a `@api.model` helper on this model, idempotent
— safe to call with pairs that already have a row) is also called from:
- `project.task.create()` / `write()` (`models/project_task.py`), whenever
  the native **Assignees** field (`user_ids`) gains someone — so assigning a
  task the normal Odoo way also makes that person show up in Resource
  Planning, at 0h, without a separate manual step.
- `account.analytic.line.create()` (`models/account_analytic_line.py`),
  whenever a timesheet is logged with both `task_id` and `employee_id` set —
  so logging time against a task is enough to appear here too, even for
  someone nobody explicitly assigned.
- `_backfill_ngyn_assignments(env)` (`__init__.py`, `post_init_hook`) — a
  one-time sweep over every existing task's assignees and every existing
  timesheet line with a task+employee, run once on install/upgrade so this
  isn't only forward-looking on a database that already had data.

In all three cases only the `(task_id, employee_id)` pair matters — the
`user_ids`→`employee_id` resolution (`res.users.employee_id`, current
company) is skipped if a user has no linked employee. Deliberately
**one-directional**: adding someone via Resource Planning does *not* add
them to the task's native Assignees — only native-Assignees-or-logged-time
→ Resource Planning, not the reverse, to avoid surprising side effects on
task notifications/kanban cards from a 0h placeholder row.

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

### `project.task` (+1 field)
| Field | Type | Purpose |
|---|---|---|
| `x_ngyn_assignment_ids` | One2many → `ngyn.task.assignment` | reverse relation, not currently shown on any view — available for future use (e.g. a smart button showing assignment count). |

**"Charged" no longer has its own custom field.** It reads the native
`project.task.allocated_hours` ("Allocated Time") directly, so it stays in
sync with Sales Orders — `sale_project` writes this field from the SO
line's quantity on confirmation/quantity change, with no separate manual
entry needed. If a task wasn't created from a Sales Order, `allocated_hours`
is just a plain field, settable directly on the task form like any other
Odoo field. (`x_ngyn_charged_hours` existed in versions before 1.0.6 —
removed once this was pointed out as unnecessary duplication.)

### `hr.employee` (+2 fields)
| Field | Type | Default | Purpose |
|---|---|---|---|
| `x_ngyn_weekly_target_hours` | Float | 28.0 | The "70% buffer" planning target per week. Configurable per person/role since some roles (PM, principal) sustain a lower percentage due to admin/meeting load. |
| `x_ngyn_weekly_hard_hours` | Float | 40.0 | Full weekly capacity. Scheduling past this is flagged red in the weekly load strip. |

## Models read but never written by this module

- **`project.project`** — `name`, `partner_id`, `date_start`, `date` (the
  Enterprise "Expiration Date"/deadline field). If these dates are unset for a
  project, health status can't be computed (see `docs/ARCHITECTURE.md`).
  Queried with `is_internal_project = False` and `is_template = False` —
  the same exclusions the stock Project app's own actions apply — so the
  per-company auto-created "Internal" project (`hr_timesheet`'s
  `res.company.internal_project_id`, with its default "Meeting"/"Training"
  tasks) and any project templates don't show up here either.
- **`account.analytic.line`** (Timesheets) — `task_id`, `employee_id`, `date`,
  `unit_amount`. Used two ways:
  1. Bucketed into week-index buckets client-side to show "actual hours" on
     locked past-week cells (per task, per employee).
  2. Summed per-project (regardless of task) via `webReadGroup` for the
     project-level "% logged" health metric — this is intentionally broader
     than the per-task actuals, since some logged time may not be tied to a
     specific task.
- **`hr.employee`** for the base fields (`name`, `job_id`) used to display
  role — `job_id` is the structured "Job Position" Many2one (`hr.job`), set
  from the employee's Work tab (or via Recruitment > Job Positions). An
  employee with no job position assigned falls back to "Team Member".

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
