# Development

## Prerequisites

- Odoo 19.0 **Enterprise** source (this module was written against v19
  Enterprise's documented APIs; it has not been tested against Community —
  it should work, since nothing here depends on an Enterprise-only app, but
  `project.project.date_start`/`date` are more reliably present out-of-the-box
  in Enterprise's Project app).
- A Postgres database Odoo can connect to.
- Python matching your Odoo version's requirement (see Odoo's own
  `requirements.txt`).

## Local install

```bash
# from your Odoo addons-path parent directory
git clone <this-repo-url>
ln -s $(pwd)/ngyn-resource-planning/ngyn_resource_planning /path/to/odoo/addons/ngyn_resource_planning
# or just copy the folder in directly instead of symlinking

./odoo-bin -d your_database -u ngyn_resource_planning --stop-after-init
# then start normally and enable the module from Apps if not auto-installed
```

When iterating on the JS/XML/SCSS during development, Odoo's asset bundle
watches for changes if you're running with `--dev=all` (or at minimum
`--dev=xml`) — otherwise you need to manually clear the assets bundle
(Settings → Technical → Regenerate Assets Bundles, in developer mode) or hard-
refresh after restarting the server.

Python model changes (new fields, new models) require `-u ngyn_resource_planning`
(module update) to apply; a server restart alone is not enough.

## Where to make common changes

See the table in `CLAUDE.md` — "Quick map: I want to change X, where do I
look?" This file focuses on *how* to work, not *where*.

## Testing — currently a gap

**There is no `tests/` folder yet.** This is the most important thing to add
next if you're extending this module. Suggested starting points, roughly in
priority order:

1. **Python unit tests** (`tests/test_resource_assignment.py`) for:
   - The SQL uniqueness constraints on both new models.
   - `scheduled_hours`/`unscheduled_hours` compute correctness, including edge
     cases (no week lines yet, `alloc_hours` changed after week lines exist).
   - Cascade deletes (deleting a task should clean up its assignments and week
     lines; deleting an employee likewise).

2. **JS/QWeb tests** — Odoo has a `hoot` test framework for OWL components in
   recent versions; a first test suite should at minimum cover:
   - `projectStats()` health-status thresholds (the three branches: red/amber/
     green, plus the "no dates set" null case).
   - `dateToWeekIdx` / `weekDate` round-tripping (a date converted to an index
     and back should land on the same Monday).
   - `taskComputed()` / `projectAllocationStats()` arithmetic.

3. **A manual QA checklist** (even before automated tests exist) should at
   minimum cover: creating an assignment, entering/clearing weekly hours
   (verify the underlying `ngyn.task.assignment.week` row is created/updated/
   deleted correctly, not just zeroed), paging the week navigator forward past
   a project's schedule end (verify the "outside schedule" warning appears),
   and crossing from a future week into a past week as "today" changes
   (requires either mocking the date or waiting — flagged as a known gap in
   `CLAUDE.md`, since `CURRENT_WEEK_IDX` is computed once at load time).

## Known rough edges to be aware of while developing

- `loadData()` re-fetches *everything* on every call — there's a
  `reloadProject(projectId)` method stubbed out that currently just calls
  `loadData()` again instead of doing a scoped refetch. Fine at current scale
  (~100 projects), but worth fixing before scaling further — see
  `docs/ROADMAP.md`.
- Optimistic local-state updates on write are not rolled back on failure
  (`onAllocChange`/`onWeekChange` show a toast notification but leave the
  stale local value in place). Low risk in practice (writes to these simple
  models rarely fail), but worth fixing if you add validation constraints that
  could realistically reject a write.
- No debounce beyond "fires on blur/Enter" (the `change` event) — this was
  intentional (avoids firing an RPC per keystroke) but means rapid tabbing
  through many cells fires one RPC per cell sequentially, not batched. Fine at
  current usage patterns; would want batching if a "fill this row" or paste-
  from-Excel feature is ever added.

## Style conventions

- Python: standard PEP 8, matches existing Odoo core module style.
- JS: matches the surrounding file's existing style (double quotes, semicolons,
  4-space indent) — no linter config is checked in yet; adding one (eslint
  config matching Odoo's own, if you want strict parity) is a reasonable
  addition.
- SCSS: all rules scoped under `.o_ngyn_rp` to avoid leaking into the rest of
  the Odoo backend UI. Keep it that way — don't add unscoped global selectors.
