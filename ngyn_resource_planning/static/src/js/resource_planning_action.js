/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

/* =========================================================
   Week timeline helpers
   A continuous, stable week index shared by the whole app:
   idx 0 = Monday, 26 weeks before "today"'s Monday.
   Paging the visible window never changes what week an idx
   points to — it only changes which slice is shown.
   ========================================================= */
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const WINDOW_SIZE = 14;
const TOTAL_WEEKS = 104; // ~2 years of coverage

function mondayOf(d) {
    const day = (d.getDay() + 6) % 7; // 0 = Monday
    const m = new Date(d);
    m.setHours(0, 0, 0, 0);
    m.setDate(m.getDate() - day);
    return m;
}
function toIso(d) {
    // Local Y/M/D, not d.toISOString() — that converts to UTC first and can shift the calendar day.
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}
function parseDateOnly(str) {
    // new Date("YYYY-MM-DD") parses as UTC midnight, which reads back as the wrong local day.
    const [y, m, d] = str.split("-").map(Number);
    return new Date(y, m - 1, d);
}
function roundQuarter(v) {
    return Math.round(v * 4) / 4;
}

const TODAY = new Date();
const ANCHOR = new Date(mondayOf(TODAY).getTime() - 26 * WEEK_MS);

function weekDate(idx) {
    return new Date(ANCHOR.getTime() + idx * WEEK_MS);
}
function weekLabel(idx) {
    return weekDate(idx).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
function dateToWeekIdx(d) {
    return Math.round((mondayOf(d) - ANCHOR) / WEEK_MS);
}

const CURRENT_WEEK_IDX = dateToWeekIdx(TODAY);

const AVATAR_PALETTE = ["#2F5D8A", "#C1611F", "#3D7A5D", "#A87B12", "#6B4C7A", "#2E7A78", "#B5402C", "#55636F"];
function initials(name) {
    const p = (name || "?").trim().split(/\s+/);
    return ((p[0][0] || "") + (p[p.length - 1][0] || "")).toUpperCase();
}
function avatarColor(id) {
    return AVATAR_PALETTE[id % AVATAR_PALETTE.length];
}

const HEALTH_LABEL = { green: "On track", amber: "Stalled", red: "Over burn" };
const HEALTH_DEF = {
    green: "On track — hours logged are tracking closely with time elapsed.",
    amber: "Stalled — time elapsed is well ahead of hours logged. Work may be blocked.",
    red: "Over burn — hours logged are running well ahead of time elapsed. This project may exceed its charged hours before the deadline.",
};
const STAT_DEF = {
    charged: "Hours sold or charged to the client for this project.",
    allocated: "Hours assigned to team members across all tasks so far.",
    leftToAssign: "Charged hours not yet assigned to anyone.",
    unscheduled: "Assigned hours that haven't been placed into a specific week yet.",
};
const PAST_LOAD_TIP = "Actual hours logged this week (past — not part of the live plan).";

export class NgynResourcePlanning extends Component {
    static template = "ngyn_resource_planning.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            projects: [],
            employees: [],
            pinned: [],
            activeFilter: new Set(), // empty = "All"
            sortMode: "health",
            searchQuery: "",
            collapsedProjects: new Set(),
            collapsedTasks: new Set(),
            weeklyLoadFilter: new Set(),
            capSearch: "",
            capRoleFilter: new Set(), // empty = "All roles"
            capCollapsed: false,
            windowStart: CURRENT_WEEK_IDX,
            openPicker: null, // {taskId}
            pickerRoleFilter: new Set(), // empty = "All"
        });

        onWillStart(() => this.loadData());
    }

    /* =====================================================
       DATA LOADING
       ===================================================== */
    async loadData() {
        const projects = await this.orm.searchRead(
            "project.project",
            // Same exclusions the stock Project app's own actions apply (project/hr_timesheet's
            // is_internal_project/is_template domain) — otherwise the per-company auto-created
            // "Internal" project (and any templates) shows up here even though it's hidden there.
            [["active", "=", true], ["is_internal_project", "=", false], ["is_template", "=", false]],
            ["name", "partner_id", "date_start", "date"],
            { limit: 300, order: "date asc" }
        );
        const projectIds = projects.map((p) => p.id);

        const tasks = projectIds.length
            ? await this.orm.searchRead(
                  "project.task",
                  [["project_id", "in", projectIds], ["active", "=", true]],
                  // allocated_hours is native project.task ("Allocated Time") -- Charged reads this
                  // directly so it stays in sync with Sales Order quantities (sale_project writes
                  // it on order confirmation/qty change) instead of needing separate manual entry.
                  ["name", "project_id", "allocated_hours"]
              )
            : [];
        const taskIds = tasks.map((t) => t.id);

        const assignments = taskIds.length
            ? await this.orm.searchRead(
                  "ngyn.task.assignment",
                  [["task_id", "in", taskIds]],
                  ["task_id", "employee_id", "alloc_hours"]
              )
            : [];
        const assignmentIds = assignments.map((a) => a.id);

        const weekLines = assignmentIds.length
            ? await this.orm.searchRead(
                  "ngyn.task.assignment.week",
                  [["assignment_id", "in", assignmentIds]],
                  ["assignment_id", "week_start_date", "hours"]
              )
            : [];

        const employees = await this.orm.searchRead(
            "hr.employee",
            [["active", "=", true]],
            ["name", "job_id", "x_ngyn_weekly_target_hours", "x_ngyn_weekly_hard_hours"]
        );

        const tsDomain = taskIds.length
            ? [["task_id", "in", taskIds], ["employee_id", "!=", false],
               ["date", ">=", toIso(weekDate(0))], ["date", "<=", toIso(TODAY)]]
            : null;
        const tsLines = tsDomain
            ? await this.orm.searchRead("account.analytic.line", tsDomain, ["task_id", "employee_id", "date", "unit_amount"])
            : [];

        const loggedGroups = projectIds.length
            ? (await this.orm.webReadGroup(
                  "account.analytic.line",
                  [["project_id", "in", projectIds]],
                  ["project_id"],
                  ["unit_amount:sum"]
              )).groups
            : [];
        const loggedByProject = {};
        loggedGroups.forEach((g) => {
            if (g.project_id) loggedByProject[g.project_id[0]] = g["unit_amount:sum"];
        });

        this.state.employees = employees.map((e) => ({
            id: e.id,
            name: e.name,
            role: e.job_id ? e.job_id[1] : "Team Member",
            target: e.x_ngyn_weekly_target_hours || 28,
            hard: e.x_ngyn_weekly_hard_hours || 40,
        }));

        this.state.projects = projects.map((p) => {
            const pTasks = tasks
                .filter((t) => t.project_id && t.project_id[0] === p.id)
                .map((t) => {
                    const tAssignments = assignments
                        .filter((a) => a.task_id && a.task_id[0] === t.id)
                        .map((a) => {
                            const weeks = {};
                            weekLines
                                .filter((w) => w.assignment_id && w.assignment_id[0] === a.id)
                                .forEach((w) => {
                                    weeks[dateToWeekIdx(parseDateOnly(w.week_start_date))] = { id: w.id, hours: w.hours };
                                });
                            const actuals = {};
                            tsLines
                                .filter(
                                    (l) =>
                                        l.task_id && l.task_id[0] === t.id &&
                                        l.employee_id && a.employee_id && l.employee_id[0] === a.employee_id[0]
                                )
                                .forEach((l) => {
                                    const idx = dateToWeekIdx(parseDateOnly(l.date));
                                    actuals[idx] = roundQuarter((actuals[idx] || 0) + l.unit_amount);
                                });
                            return {
                                id: a.id,
                                employeeId: a.employee_id ? a.employee_id[0] : false,
                                employeeName: a.employee_id ? a.employee_id[1] : "",
                                alloc: a.alloc_hours,
                                weeks,
                                actuals,
                            };
                        });
                    return {
                        id: t.id,
                        name: t.name,
                        charged: t.allocated_hours || 0,
                        assignments: tAssignments,
                    };
                });
            const charged = pTasks.reduce((s, t) => s + t.charged, 0);
            return {
                id: p.id,
                name: p.name,
                client: p.partner_id ? p.partner_id[1] : "",
                dateStart: p.date_start,
                dateEnd: p.date,
                charged,
                loggedHours: loggedByProject[p.id] || 0,
                tasks: pTasks,
            };
        });

        // Auto-pin the two most urgent (over-burn, soonest deadline) projects
        // so the workspace isn't empty on first open.
        const worst = this.state.projects
            .map((p) => ({ p, s: this.projectStats(p) }))
            .filter((x) => x.s.status === "red")
            .sort((a, b) => a.s.daysLeft - b.s.daysLeft)
            .slice(0, 2)
            .map((x) => x.p.id);
        this.state.pinned = worst;

        this.state.loading = false;
    }

    async reloadProject(projectId) {
        // Lightweight refresh of a single project's tasks/assignments after a write,
        // to pick up server-computed fields without a full reload.
        await this.loadData();
    }

    /* =====================================================
       WEEK TIMELINE / NAVIGATOR
       ===================================================== */
    visibleWeeks() {
        const out = [];
        for (let i = 0; i < WINDOW_SIZE; i++) {
            const idx = this.state.windowStart + i;
            out.push({ idx, label: weekLabel(idx) });
        }
        return out;
    }
    get weekNavLabel() {
        const w = this.visibleWeeks();
        return `${w[0].label} – ${w[w.length - 1].label}`;
    }
    get canGoPrev() {
        return this.state.windowStart > 0;
    }
    get canGoNext() {
        return this.state.windowStart + WINDOW_SIZE < TOTAL_WEEKS;
    }
    prevWeekBatch() {
        this.state.windowStart = Math.max(0, this.state.windowStart - WINDOW_SIZE);
    }
    nextWeekBatch() {
        this.state.windowStart = Math.min(TOTAL_WEEKS - WINDOW_SIZE, this.state.windowStart + WINDOW_SIZE);
    }
    jumpToday() {
        this.state.windowStart = CURRENT_WEEK_IDX;
    }

    /* =====================================================
       COMPUTED: health / allocation stats
       ===================================================== */
    projectStats(p) {
        let elapsedPct = null;
        let daysLeft = null;
        if (p.dateStart && p.dateEnd) {
            const start = parseDateOnly(p.dateStart);
            const end = parseDateOnly(p.dateEnd);
            const totalDays = (end - start) / 86400000;
            const elapsedDays = Math.min(Math.max((TODAY - start) / 86400000, 0), totalDays);
            elapsedPct = totalDays > 0 ? (elapsedDays / totalDays) * 100 : 100;
            daysLeft = Math.ceil((end - TODAY) / 86400000);
        }
        const loggedPct = p.charged > 0 ? (p.loggedHours / p.charged) * 100 : 0;
        let status = "green";
        if (elapsedPct !== null) {
            const diff = loggedPct - elapsedPct;
            if (diff > 15) status = "red";
            else if (diff < -20) status = "amber";
        }
        return { elapsedPct, loggedPct, status, daysLeft };
    }
    healthLabel(status) {
        return HEALTH_LABEL[status];
    }
    healthTip(p) {
        const s = this.projectStats(p);
        const nums = s.elapsedPct !== null
            ? ` (${s.loggedPct.toFixed(0)}% logged vs ${s.elapsedPct.toFixed(0)}% elapsed)`
            : " (no start/deadline set)";
        return HEALTH_DEF[s.status] + nums;
    }
    taskComputed(task) {
        const allocated = task.assignments.reduce((s, a) => s + a.alloc, 0);
        const scheduled = task.assignments.reduce(
            (s, a) => s + Object.values(a.weeks).reduce((x, y) => x + y.hours, 0),
            0
        );
        return { allocated, leftToAssign: task.charged - allocated, unscheduled: allocated - scheduled };
    }
    projectAllocationStats(p) {
        const allocated = p.tasks.reduce((s, t) => s + this.taskComputed(t).allocated, 0);
        const unscheduled = p.tasks.reduce((s, t) => s + this.taskComputed(t).unscheduled, 0);
        return { charged: p.charged, allocated, leftToAssign: p.charged - allocated, unscheduled };
    }
    statTip(key) {
        return STAT_DEF[key];
    }
    projectWeekRange(p) {
        if (!p.dateStart || !p.dateEnd) return [0, TOTAL_WEEKS - 1];
        return [dateToWeekIdx(parseDateOnly(p.dateStart)), dateToWeekIdx(parseDateOnly(p.dateEnd))];
    }
    fmtDate(dstr) {
        if (!dstr) return "—";
        return parseDateOnly(dstr).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }
    weekHours(assignment, weekIdx) {
        const w = assignment.weeks[weekIdx];
        return w ? w.hours : 0;
    }
    displayHours(v) {
        return v > 0 ? v : "";
    }
    actualHours(assignment, weekIdx) {
        return assignment.actuals[weekIdx] || 0;
    }
    inSchedule(project, weekIdx) {
        const r = this.projectWeekRange(project);
        return weekIdx >= r[0] && weekIdx <= r[1];
    }
    projectOutOfWindow(project) {
        const r = this.projectWeekRange(project);
        const vs = this.state.windowStart;
        const ve = this.state.windowStart + WINDOW_SIZE - 1;
        return r[1] < vs || r[0] > ve;
    }

    /* =====================================================
       LEFT PANE — filter / sort / pin
       ===================================================== */
    get filteredProjects() {
        const q = this.state.searchQuery.trim().toLowerCase();
        let list = this.state.projects.map((p) => ({ p, stats: this.projectStats(p) }));
        if (q) list = list.filter(({ p }) => (p.name + " " + p.client).toLowerCase().includes(q));
        if (this.state.activeFilter.has("unallocated")) {
            list = list.filter(({ p }) => this.projectAllocationStats(p).leftToAssign > 0);
        }
        if (this.state.sortMode === "health") {
            const rank = { red: 0, amber: 1, green: 2 };
            list.sort((a, b) => rank[a.stats.status] - rank[b.stats.status] ||
                (a.stats.daysLeft ?? 9999) - (b.stats.daysLeft ?? 9999));
        } else if (this.state.sortMode === "deadline") {
            list.sort((a, b) => (a.stats.daysLeft ?? 9999) - (b.stats.daysLeft ?? 9999));
        } else {
            list.sort((a, b) => a.p.name.localeCompare(b.p.name));
        }
        return list.map((x) => x.p);
    }
    // Count of projects with hours still left to assign to anyone (charged > allocated) --
    // the thing the "Left to assign" filter chip counts and filters on.
    get unallocatedCount() {
        return this.state.projects.filter((p) => this.projectAllocationStats(p).leftToAssign > 0).length;
    }
    get pinnedProjects() {
        return this.state.pinned.map((id) => this.state.projects.find((p) => p.id === id)).filter(Boolean);
    }
    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }
    setFilter(f) {
        this._toggleFilterSet(this.state.activeFilter, f);
    }
    onSortChange(ev) {
        this.state.sortMode = ev.target.value;
    }
    togglePin(id) {
        const i = this.state.pinned.indexOf(id);
        if (i === -1) this.state.pinned.push(id);
        else this.state.pinned.splice(i, 1);
    }
    isPinned(id) {
        return this.state.pinned.includes(id);
    }

    /* =====================================================
       COLLAPSE CONTROLS
       ===================================================== */
    isProjectCollapsed(id) {
        return this.state.collapsedProjects.has(id);
    }
    toggleProjectCollapse(id) {
        if (this.state.collapsedProjects.has(id)) this.state.collapsedProjects.delete(id);
        else this.state.collapsedProjects.add(id);
    }
    collapseAllProjects() {
        this.state.pinned.forEach((id) => this.state.collapsedProjects.add(id));
    }
    expandAllProjects() {
        this.state.pinned.forEach((id) => this.state.collapsedProjects.delete(id));
    }
    isTaskCollapsed(projectId, taskId) {
        return this.state.collapsedTasks.has(`${projectId}_${taskId}`);
    }
    toggleTaskCollapse(projectId, taskId) {
        const key = `${projectId}_${taskId}`;
        if (this.state.collapsedTasks.has(key)) this.state.collapsedTasks.delete(key);
        else this.state.collapsedTasks.add(key);
    }
    collapseAllTasks(project) {
        project.tasks.forEach((t) => this.state.collapsedTasks.add(`${project.id}_${t.id}`));
    }
    expandAllTasks(project) {
        project.tasks.forEach((t) => this.state.collapsedTasks.delete(`${project.id}_${t.id}`));
    }
    unpinProject(id, ev) {
        ev.stopPropagation();
        this.state.pinned = this.state.pinned.filter((x) => x !== id);
    }

    /* =====================================================
       PLANNING GRID — edits (write on change, quarter-hour rounding)
       ===================================================== */
    async onAllocChange(assignment, ev) {
        const v = roundQuarter(parseFloat(ev.target.value) || 0);
        assignment.alloc = v;
        try {
            await this.orm.write("ngyn.task.assignment", [assignment.id], { alloc_hours: v });
        } catch (e) {
            this.notification.add("Could not save that hour value.", { type: "danger" });
        }
    }
    async onWeekChange(assignment, weekIdx, ev) {
        const v = roundQuarter(parseFloat(ev.target.value) || 0);
        const existing = assignment.weeks[weekIdx];
        const weekDateStr = toIso(weekDate(weekIdx));
        try {
            if (existing && existing.id) {
                if (v > 0) {
                    await this.orm.write("ngyn.task.assignment.week", [existing.id], { hours: v });
                    assignment.weeks[weekIdx] = { id: existing.id, hours: v };
                } else {
                    await this.orm.unlink("ngyn.task.assignment.week", [existing.id]);
                    delete assignment.weeks[weekIdx];
                }
            } else if (v > 0) {
                const newIds = await this.orm.create("ngyn.task.assignment.week", [
                    { assignment_id: assignment.id, week_start_date: weekDateStr, hours: v },
                ]);
                assignment.weeks[weekIdx] = { id: newIds[0], hours: v };
            }
        } catch (e) {
            this.notification.add("Could not save that hour value.", { type: "danger" });
        }
    }

    /* =====================================================
       ADD TEAM MEMBER (role-filtered picker)
       ===================================================== */
    get roles() {
        return [...new Set(this.state.employees.map((e) => e.role))].sort();
    }
    // Shared by every multi-select chip cloud (health filter, both role filters):
    // "all" clears the whole selection; otherwise toggles that one value in/out of it.
    _toggleFilterSet(set, value) {
        if (value === "all") set.clear();
        else if (set.has(value)) set.delete(value);
        else set.add(value);
    }
    isPickerOpen(taskId) {
        return this.state.openPicker && this.state.openPicker.taskId === taskId;
    }
    toggleAddMember(task, ev) {
        ev.stopPropagation();
        const opening = !this.isPickerOpen(task.id);
        this.state.openPicker = opening ? { taskId: task.id } : null;
        if (opening) this.state.pickerRoleFilter.clear();
    }
    setPickerRole(role, ev) {
        ev.stopPropagation();
        this._toggleFilterSet(this.state.pickerRoleFilter, role);
    }
    pickerMembers() {
        return this.state.employees.filter(
            (e) => this.state.pickerRoleFilter.size === 0 || this.state.pickerRoleFilter.has(e.role)
        );
    }
    async addAssignment(task, employee, ev) {
        ev.stopPropagation();
        if (task.assignments.some((a) => a.employeeId === employee.id)) {
            this.state.openPicker = null;
            return;
        }
        try {
            const newIds = await this.orm.create("ngyn.task.assignment", [
                { task_id: task.id, employee_id: employee.id, alloc_hours: 0 },
            ]);
            task.assignments.push({
                id: newIds[0],
                employeeId: employee.id,
                employeeName: employee.name,
                alloc: 0,
                weeks: {},
                actuals: {},
            });
        } catch (e) {
            this.notification.add("Could not add that team member.", { type: "danger" });
        }
        this.state.openPicker = null;
    }

    /* =====================================================
       PIN-TO-WEEKLY-LOAD (shared toggle, no persistence needed)
       ===================================================== */
    isEmployeePinned(employeeId) {
        return this.state.weeklyLoadFilter.has(employeeId);
    }
    toggleEmployeePin(employeeId, ev) {
        ev.stopPropagation();
        if (this.state.weeklyLoadFilter.has(employeeId)) this.state.weeklyLoadFilter.delete(employeeId);
        else this.state.weeklyLoadFilter.add(employeeId);
    }

    /* =====================================================
       WEEKLY LOAD STRIP
       ===================================================== */
    toggleCapCollapsed() {
        this.state.capCollapsed = !this.state.capCollapsed;
    }
    onCapSearchInput(ev) {
        this.state.capSearch = ev.target.value;
    }
    setCapRoleFilter(role) {
        this._toggleFilterSet(this.state.capRoleFilter, role);
    }
    get filteredCapEmployees() {
        const q = this.state.capSearch.trim().toLowerCase();
        return this.state.employees.filter((e) => {
            if (this.state.capRoleFilter.size > 0 && !this.state.capRoleFilter.has(e.role)) return false;
            if (q && !(e.name + " " + e.role).toLowerCase().includes(q)) return false;
            if (this.state.weeklyLoadFilter.size > 0 && !this.state.weeklyLoadFilter.has(e.id)) return false;
            return true;
        });
    }
    weekTotalForEmployee(employeeId, weekIdx, isPast) {
        let total = 0;
        this.state.projects.forEach((p) => {
            p.tasks.forEach((t) => {
                t.assignments.forEach((a) => {
                    if (a.employeeId !== employeeId) return;
                    if (isPast) {
                        if (a.actuals[weekIdx]) total += a.actuals[weekIdx];
                    } else if (a.weeks[weekIdx]) {
                        total += a.weeks[weekIdx].hours;
                    }
                });
            });
        });
        return roundQuarter(total);
    }
    capCellTier(total, emp) {
        if (total > emp.hard) return "red";
        if (total > emp.target) return "amber";
        return "green";
    }
    capCellTip(total, emp) {
        const free = roundQuarter(emp.target - total);
        const freeTail = free >= 0 ? `${free}h free before the buffer is used up.` : `${Math.abs(free)}h over the buffer.`;
        return `${total}h allocated this week, of a ${emp.target}h/wk buffer target (${emp.hard}h hard capacity). ${freeTail}`;
    }
    pastLoadTip() {
        return PAST_LOAD_TIP;
    }
    capEmptyReason() {
        return this.state.weeklyLoadFilter.size > 0
            ? "No pinned team member matches the current search/role filter."
            : `No team member matches "${this.state.capSearch}".`;
    }

    /* =====================================================
       DISPLAY HELPERS
       ===================================================== */
    initials(name) {
        return initials(name);
    }
    avatarColor(id) {
        return avatarColor(id || 0);
    }
    isPastWeek(idx) {
        return idx < CURRENT_WEEK_IDX;
    }
}

registry.category("actions").add("ngyn_resource_planning.dashboard", NgynResourcePlanning);
