# Roadmap / known limitations

This is the authoritative list of what v1.0.0 intentionally left out or
simplified. Treat this as the backlog — roughly ordered by what would matter
most for a wider rollout, not by effort.

## Security

- [ ] **Differentiate access rights.** Currently `base.group_user` (any
  internal/logged-in user) has full CRUD on both `ngyn.task.assignment` and
  `ngyn.task.assignment.week`. Needs at minimum: project managers can edit
  anything on their projects; other users can view but not edit, or can only
  edit assignments where they're the assigned employee. Likely implemented via
  `ir.rule` record rules referencing `project.task.project_id` membership,
  once it's clear how the client wants this scoped.
- [ ] Consider whether `project.task.allocated_hours` should be read-only
  for non-managers here (it's effectively the billing budget, and is
  writable directly on the task form already via stock Odoo).

## Data & performance

- [ ] **Server-side pagination / filtering for the left pane.** `loadData()`
  currently fetches up to 300 active projects in one call and does all
  filtering/sorting client-side. Fine at ~100 projects; will need a proper
  paginated/searched approach if the portfolio grows substantially, or if
  "active" projects alone exceed a few hundred.
- [ ] **Scoped refetch instead of full reload.** `reloadProject()` is a stub
  that just calls `loadData()` again. A real implementation should refetch
  only the changed project's tasks/assignments.
- [ ] No optimistic-update rollback on write failure (see `docs/DEVELOPMENT.md`).
- [ ] `CURRENT_WEEK_IDX` is computed once when the component mounts. If a user
  keeps the tab open across midnight (particularly the Sunday→Monday boundary
  where a new "current week" begins), past/future week locking won't update
  until they reload. Low-impact, but worth a periodic re-check if this becomes
  a real workflow (e.g. an overnight dashboard display).

## UX parity with the original design (deferred, not forgotten)

These were present in the interactive mockup this module was built from, and
were consciously cut for v1 to reduce risk on first install — not oversights:

- [ ] Styled hover-tooltip popovers (currently plain `title` attributes) for
  health status, buffer tiers, and stat labels.
- [ ] Horizontal scroll-sync across all visible grids (planning grids + weekly
  load table) — column *alignment* is preserved (fixed table layout, matching
  widths), but scrolling one doesn't move the others together.
- [ ] Avatar/initials color consistency was ported; double-check it still
  reads well against the actual Odoo Enterprise theme (built against the
  mockup's own color palette, not Odoo's default backend theme variables).

## Feature ideas raised but not committed to v1

- [ ] Bulk-fill / paste-from-Excel for weekly hour entry (would need RPC
  batching — see `docs/DEVELOPMENT.md`).
- [ ] A "my assignments" personal view for non-manager employees, separate
  from the full multi-project workspace.
- [ ] Notifications/digest when a project crosses into "Over burn."
- [ ] Exporting the weekly load strip (or a filtered slice of it) to a
  spreadsheet.

## Code health

- [ ] No automated tests exist (`docs/DEVELOPMENT.md` has suggested starting
  points — this is the single highest-value next contribution).
- [ ] Single-file component/template — fine for now, but if the codebase grows,
  split into sub-components (see `docs/ARCHITECTURE.md` §"Component structure").
- [ ] No CI configured yet (no GitHub Actions workflow in this repo). At
  minimum, a workflow that runs `python -m py_compile` on the models and
  validates the XML files would catch the most common breakage cheaply.
