# Architecture

## Overview

This module is one Odoo **OWL client action** (`ngyn_resource_planning.dashboard`),
registered under a single top-level menu, reading and writing standard Odoo
records via the `orm` service. It is deliberately *not* built with the standard
list/kanban/form view framework — the two-pane, multiple-projects-pinned-at-once
layout doesn't map onto those view types.

```
Browser
  └─ OWL client action (resource_planning_action.js)
       ├─ state: useState({...})              — all UI/interaction state
       ├─ loadData()                          — one-time bulk fetch on mount
       ├─ business-rule methods               — health calc, buffer tiers, etc.
       └─ write-back methods                  — orm.write/create/unlink on edit
              ↕
       QWeb template (resource_planning_templates.xml)
              ↕
Odoo ORM (project.project, project.task, hr.employee,
          ngyn.task.assignment, ngyn.task.assignment.week,
          account.analytic.line [read-only])
```

## Data flow

1. **`onWillStart` → `loadData()`** fires once when the action opens. It issues
   a handful of `searchRead`/`webReadGroup` calls (not one per row — see
   `docs/DEVELOPMENT.md` for the batching rationale) and assembles everything
   into `this.state.projects` — a nested JS structure:
   `project → tasks → assignments → { weeks: {idx: {id, hours}}, actuals: {idx: hours} }`.

2. **All derived numbers are computed client-side, live**, from that nested
   structure — `projectStats()`, `taskComputed()`, `projectAllocationStats()`,
   `weekTotalForEmployee()`, etc. are plain methods called directly from the
   template on every render. There is no server round-trip for these; editing
   an hour value updates the local state object, and every dependent number
   (header stats, weekly-load totals, health status) recomputes on the next
   render automatically because Owl's reactivity tracks the mutation.

3. **Persistence happens on the `change` event** (blur/Enter), not on every
   keystroke — `onAllocChange()` / `onWeekChange()` call `orm.write` /
   `orm.create` / `orm.unlink` directly against `ngyn.task.assignment` /
   `ngyn.task.assignment.week`, then patch the same local state object so the
   UI doesn't need a full reload.

There is currently **no client-side cache invalidation or refetch on write
failure** beyond a notification toast — if a write fails, the optimistic local
update is *not* rolled back. This is a known gap (see `docs/ROADMAP.md`).

## Week timeline (the trickiest part)

Every week in the app is identified by a plain integer index, not a date
object, computed against a fixed anchor:

```js
const ANCHOR = mondayOf(today) - 26 weeks;   // computed once at module load
weekDate(idx)      = ANCHOR + idx * 7 days;   // idx → real Monday date
dateToWeekIdx(d)    = round((mondayOf(d) - ANCHOR) / 7days);  // date → idx
CURRENT_WEEK_IDX    = dateToWeekIdx(today);   // fixed at load time
```

`TOTAL_WEEKS = 104` (about 2 years) is the full addressable range;
`WINDOW_SIZE = 14` is how many week columns are visible at once.
`state.windowStart` is the index of the first visible column — paging forward/
back moves this by a full `WINDOW_SIZE` batch; "Today" resets it to
`CURRENT_WEEK_IDX`.

**Why this matters:** `ngyn.task.assignment.week.week_start_date` is always
written as a real Monday date (`toIso(weekDate(idx))`), so the underlying data
is calendar-real and portable — but all *UI* logic (locking past weeks, range-
checking a project's schedule, laying out the grid) works in index space. This
means paging the visible window is purely a UI concern and can never
accidentally shift which calendar week an hour belongs to. If you ever need to
extend the range, widen `TOTAL_WEEKS` and/or push `ANCHOR` further back — don't
change the indexing scheme itself without checking every place `weekIdx` is
used as an object key (JS coerces numeric keys to strings, which is fine, but
be consistent).

## Business rules (exact formulas)

### Project health status

```
elapsedPct = clamp((today - date_start) / (date - date_start), 0, 1) * 100
loggedPct  = (total hours logged on this project via Timesheets) / charged * 100
diff       = loggedPct - elapsedPct

diff > 15   → "red"   (Over burn)
diff < -20  → "amber" (Stalled)
else        → "green" (On track)
```
If a project has no `date_start` or `date` (deadline), `elapsedPct` is `null`
and status defaults to green (can't assess without a schedule). This is a
judgment call, not a hard requirement — revisit if it causes confusion.

Note the asymmetry: over-burning is flagged 5 points more sensitively than
stalling. This was a deliberate choice during design (burning through budget
is the more urgent risk to catch early).

### Task/project allocation reconciliation

```
allocated       = Σ ngyn.task.assignment.alloc_hours for the task
leftToAssign    = task.charged - allocated          (can go negative — over-allocated)
scheduled       = Σ ngyn.task.assignment.week.hours for the task
unscheduled     = allocated - scheduled              (given to someone, not yet placed on a week)
```
Project-level numbers are the sum of these across all the project's tasks.

### Weekly capacity / buffer tiers

```
total = Σ hours a person is scheduled across ALL projects, for one week
        (from .weeks for current/future weeks, from .actuals for past weeks)

total ≤ employee.target  → green  ("within buffer")
target < total ≤ hard    → amber  ("using buffer")
total > hard              → red    ("over capacity")

free = employee.target - total    (shown as "free Xh", or "over Xh" if negative)
```

## Component structure (current vs. suggested next step)

Everything currently lives in **one component, one template file**. This was a
deliberate v1 simplification (matching how the original HTML mockup was
structured) to minimize risk on first install. If the codebase grows —
especially if per-cell interactions get more complex — the natural refactor is
sub-components:

- `ProjectListRow` (left pane row)
- `ProjectCard` (pinned project header + grid)
- `WeekCell` (single editable/locked cell — this logic is currently duplicated
  between the planning grid and, in simplified form, the weekly load strip)
- `WeeklyLoadStrip`
- `AddMemberPicker`

None of this is done yet. Don't split it preemptively without a concrete reason
(e.g., a feature that genuinely needs component-local state) — see
`docs/ROADMAP.md`.
