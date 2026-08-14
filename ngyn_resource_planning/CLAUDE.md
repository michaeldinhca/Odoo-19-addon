# CLAUDE.md — context for AI coding assistants

Read this first. It's written so a fresh AI session (Claude Code, or any other
coding assistant) can understand what this project is, why it's built the way it
is, and what to do next — without re-deriving context from the code alone.

## What this is

An Odoo 19 Enterprise custom module (`ngyn_resource_planning`) that adds a
multi-project **weekly resource planning workspace**. It sits on top of the
standard `project`, `hr`, and `hr_timesheet` apps.

**The problem it solves:** the client (an engineering firm, ~20 staff, ~100
concurrent projects) bills by charged hours per task and needed a way to see,
at a glance, which projects are burning hours faster than their timeline, and
how loaded each person is *across all their projects* — not per-project, which
is all standard Odoo Project/Planning views show well.

**How it got here:** this module was built from an interactive HTML/JS mockup
that went through ~10 rounds of visual and behavioral feedback with the client
before being ported to real Odoo (OWL + ORM). That mockup is *not* in this repo,
but its accumulated decisions (health-status formula, buffer-tier thresholds,
week-timeline design, UI density choices) are what's implemented here. If a
decision in the code looks arbitrary, it probably came from a specific piece of
client feedback — check `docs/ARCHITECTURE.md` before "fixing" it.

## Read next, in this order

1. `docs/DATA_MODEL.md` — every field and model this module adds, and why. Read
   this before touching any model.
2. `docs/ARCHITECTURE.md` — how the OWL client action is structured, the week-
   timeline design (the single trickiest part of this codebase), and the
   business-rule formulas (health status, buffer tiers) with their exact
   thresholds.
3. `docs/ROADMAP.md` — what's known to be missing or simplified in v1, roughly
   prioritized. Start here when picking up new work.
4. `docs/DEVELOPMENT.md` — local setup and where to make common changes.

## Non-obvious things worth knowing before you touch the code

- **The week timeline is a single continuous index, not calendar dates directly.**
  `static/src/js/resource_planning_action.js` defines `ANCHOR` (a fixed Monday,
  26 weeks before today at module-load time) and every week is `ANCHOR + idx *
  7 days`. This is deliberate: paging the visible 14-week window must never
  reassign which calendar week a given hour is tied to. If you need to change
  the visible window size or total range, see the `WINDOW_SIZE` / `TOTAL_WEEKS`
  constants — do not refactor this into calendar-date-keyed state without
  re-reading `docs/ARCHITECTURE.md` §"Week timeline" first.

- **Three different hour numbers coexist on purpose:** `charged` (what's billed,
  on `project.task`), `allocated` (what's been given to a person, on
  `ngyn.task.assignment.alloc_hours`), and `scheduled`/`unscheduled` (whether
  those allocated hours have been placed into a specific week yet, derived from
  `ngyn.task.assignment.week`). Don't collapse these into one field — the gaps
  between them are the whole point of the UI (see `docs/DATA_MODEL.md`).

- **Past weeks are read-only and show timesheet actuals, not the plan.** This
  is computed client-side by comparing a week's index to `CURRENT_WEEK_IDX`
  (computed once at module load, not re-evaluated per render — if this module
  stays open across midnight, "today" won't update until reload; acceptable
  for v1, noted in `docs/ROADMAP.md`).

- **The health status formula is exact and was tuned with the client, not
  arbitrary.** `diff = loggedPct - elapsedPct`; `diff > 15` → Over burn (red),
  `diff < -20` → Stalled (amber), else On track (green). Don't adjust these
  thresholds without checking with the client first — they were picked
  deliberately asymmetric (burning too fast is flagged more sensitively than
  stalling).

- **Access rights are currently wide open** (`base.group_user`, full CRUD on
  both new models). This was a conscious v1 simplification, not an oversight —
  see `docs/ROADMAP.md` for the intended follow-up (PM vs. assignee vs.
  read-only).

- **No automated tests exist yet.** If you add features, please also add the
  first tests (there currently isn't even a `tests/` folder) — see
  `docs/DEVELOPMENT.md` for suggested starting points.

## Quick map: "I want to change X, where do I look?"

| Change | File |
|---|---|
| Health status thresholds / formula | `static/src/js/resource_planning_action.js` → `projectStats()` |
| Buffer/hard-capacity tiering | `static/src/js/resource_planning_action.js` → `capCellTier()` |
| Week timeline range/window size | `static/src/js/resource_planning_action.js` → top constants (`WINDOW_SIZE`, `TOTAL_WEEKS`, `ANCHOR`) |
| Add a field to the assignment model | `models/resource_assignment.py`, then expose it in `loadData()` in the JS, then render it in `static/src/xml/resource_planning_templates.xml` |
| Change what's editable vs. locked per week | `inSchedule()` / `isPastWeek()` in the JS, and the corresponding `t-if/t-elif/t-else` block in the template's week-cell `<td>` |
| Visual/layout changes | `static/src/scss/resource_planning.scss` (scoped under `.o_ngyn_rp`) |
| New menu item / server action | `views/resource_planning_menus.xml` |
| Employee form field placement | `views/hr_employee_views.xml` (xpath on `//notebook`, position `before`) — there's no equivalent task-form view file anymore, since "Charged" now reads the native `project.task.allocated_hours` field directly instead of a custom one |
| End-user documentation | `data/knowledge_articles.xml` — one root `knowledge.article`, `internal_permission: read` + an explicit `write` member for `base.partner_admin` (Knowledge has no group-based sharing, only per-person). Keep this in sync with real UI behavior when the screen changes — it's meant to be the actual end-user reference, not a stub. |
| Who auto-gets a 0h assignment row | `ngyn.task.assignment._ensure_assignments()` in `models/resource_assignment.py` is the single source of truth, called from `project_task.py` (native Assignees), `account_analytic_line.py` (logged time), and `__init__.py`'s `post_init_hook` (one-time backfill on install/upgrade). Add a new auto-membership source here, not by duplicating the create-if-missing logic elsewhere. |

## Conventions used in this codebase

- Custom fields are prefixed `x_ngyn_` to make them unambiguous in a database
  that likely has other customizations.
- Python: standard Odoo ORM conventions, no ORM shortcuts beyond what's shown.
- JS: single-file OWL component (`useState` for all reactive state, including
  `Set` instances for collapsed/pinned tracking — Owl 2's reactivity handles
  `Set`/`Map` mutation natively, no need to reassign).
- Templates: plain QWeb (`t-if`/`t-elif`/`t-else`, `t-foreach`, `t-esc`,
  `t-att-*`, `t-attf-*`) — no sub-components yet. If this file grows much
  larger, splitting into `ProjectCard`, `WeekCell`, `WeeklyLoadStrip` sub-
  components is the natural next refactor (see `docs/ROADMAP.md`).

## When you're done with a change

Update `CHANGELOG.md` (Keep a Changelog format), bump the version in
`__manifest__.py` (Odoo format: `19.0.{major}.{minor}.{patch}`), and if you
changed a documented design decision, update the relevant `docs/*.md` file so
the next AI session (or the next developer) doesn't have to rediscover it.
