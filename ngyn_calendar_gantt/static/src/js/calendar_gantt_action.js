/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { serializeDateTime, deserializeDateTime } from "@web/core/l10n/dates";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

const { DateTime } = luxon;

/* =========================================================
   Which calendar.event field rows are grouped by is chosen in
   Calendar > Configuration > Settings (res_config_settings.py,
   ngyn_calendar_gantt.groupby_field) — or from the quick picker
   in this view's own toolbar, which writes to the same param.
   This map is this file's copy of that same short list — kept
   in sync manually, same hand-rolled approach
   ngyn_resource_planning already uses for its own small lookups.
   ========================================================= */
const GROUPBY_FIELDS = {
    opportunity_id: { label: "Opportunity", type: "many2one" },
    x_ngyn_installer_ids: { label: "Installer", type: "many2many" },
};
const DEFAULT_GROUPBY = "opportunity_id";
const UNASSIGNED_KEY = "__unassigned__";
const LANE_HEIGHT = 32; // px — must match .o_ngyn_gantt_bar height + gap in the SCSS

// Business-hours window the timeline is scaled to (per user request: 6am–8pm,
// not a full 24h day). An event outside this window is visually clamped to
// the nearest edge of the window — it still shows, just compressed to the
// boundary, rather than being hidden or breaking the day-column math.
const BUSINESS_START_HOUR = 6;
const BUSINESS_END_HOUR = 20;
const BUSINESS_WINDOW_MIN = (BUSINESS_END_HOUR - BUSINESS_START_HOUR) * 60;
const HOUR_TICKS = [6, 9, 12, 15, 18];

const AVATAR_PALETTE = ["#2F5D8A", "#C1611F", "#3D7A5D", "#A87B12", "#6B4C7A", "#2E7A78", "#B5402C", "#55636F"];
function computeInitials(name) {
    const parts = (name || "?").trim().split(/\s+/);
    return ((parts[0][0] || "") + (parts[parts.length - 1][0] || "")).toUpperCase();
}
function computeAvatarColor(id) {
    return AVATAR_PALETTE[id % AVATAR_PALETTE.length];
}

function packLanes(events) {
    // Sort by start, then place each event in the first lane whose last
    // event already ends before this one starts, else open a new lane.
    // This is what actually solves the "4-5 things at once" problem — bars
    // that overlap in time are stacked instead of drawn on top of each
    // other. Lane assignment always uses the real start/stop, never the
    // business-hours-clamped display values, so true time conflicts are
    // never missed just because they render compressed.
    const sorted = [...events].sort((a, b) => a.start - b.start);
    const laneLastStop = [];
    for (const ev of sorted) {
        let lane = laneLastStop.findIndex((lastStop) => lastStop <= ev.start);
        if (lane === -1) {
            lane = laneLastStop.length;
        }
        ev.lane = lane;
        laneLastStop[lane] = ev.stop;
    }
    const lanes = laneLastStop.map(() => []);
    for (const ev of sorted) {
        lanes[ev.lane].push(ev);
    }
    return lanes;
}

export class NgynCalendarGanttTimeline extends Component {
    static template = "ngyn_calendar_gantt.Timeline";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");

        this.state = useState({
            loading: true,
            weekStart: DateTime.local().startOf("week"),
            groupbyField: DEFAULT_GROUPBY,
            searchQuery: "",
            rows: [],
        });

        onWillStart(async () => {
            const groupby = await this.orm.call("ir.config_parameter", "get_param", [
                "ngyn_calendar_gantt.groupby_field",
                DEFAULT_GROUPBY,
            ]);
            this.state.groupbyField = GROUPBY_FIELDS[groupby] ? groupby : DEFAULT_GROUPBY;
            await this.loadData();
        });
    }

    /* =====================================================
       DATA LOADING
       ===================================================== */
    async loadData() {
        this.state.loading = true;
        const field = this.state.groupbyField;
        const weekStart = this.state.weekStart;
        const weekEnd = weekStart.plus({ days: 7 });

        // Always fetch the installer field too, even when grouping by
        // Opportunity — it's needed for the per-bar installer avatars.
        const fields = new Set(["name", "start", "stop", field, "x_ngyn_installer_ids"]);

        const events = await this.orm.searchRead(
            "calendar.event",
            [
                ["start", "<", serializeDateTime(weekEnd)],
                ["stop", ">", serializeDateTime(weekStart)],
            ],
            [...fields],
            { order: "start asc" }
        );

        const installerIds = [...new Set(events.flatMap((ev) => ev.x_ngyn_installer_ids || []))];
        let partnerNames = {};
        if (installerIds.length) {
            const partners = await this.orm.read("res.partner", installerIds, ["name"]);
            partnerNames = Object.fromEntries(partners.map((p) => [p.id, p.name]));
        }

        const groups = new Map();
        const ensureGroup = (key, label) => {
            if (!groups.has(key)) {
                groups.set(key, { key, label, events: [] });
            }
            return groups.get(key);
        };

        for (const ev of events) {
            const installers = (ev.x_ngyn_installer_ids || []).map((id) => ({
                id,
                name: partnerNames[id] || `#${id}`,
            }));
            const bar = {
                id: ev.id,
                name: ev.name,
                start: deserializeDateTime(ev.start),
                stop: deserializeDateTime(ev.stop),
                installers,
            };
            if (GROUPBY_FIELDS[field].type === "many2one") {
                const value = ev[field];
                const group = value
                    ? ensureGroup(value[0], value[1])
                    : ensureGroup(UNASSIGNED_KEY, "Unassigned");
                group.events.push(bar);
            } else {
                const ids = ev[field] || [];
                if (!ids.length) {
                    ensureGroup(UNASSIGNED_KEY, "Unassigned").events.push(bar);
                } else {
                    for (const id of ids) {
                        ensureGroup(id, partnerNames[id] || `#${id}`).events.push({ ...bar });
                    }
                }
            }
        }

        const rows = [...groups.values()].sort((a, b) => {
            if (a.key === UNASSIGNED_KEY) return 1;
            if (b.key === UNASSIGNED_KEY) return -1;
            return a.label.localeCompare(b.label);
        });
        for (const row of rows) {
            row.lanes = packLanes(row.events);
        }

        this.state.rows = rows;
        this.state.loading = false;
    }

    /* =====================================================
       NAVIGATION
       ===================================================== */
    prevWeek() {
        this.state.weekStart = this.state.weekStart.minus({ days: 7 });
        this.loadData();
    }
    nextWeek() {
        this.state.weekStart = this.state.weekStart.plus({ days: 7 });
        this.loadData();
    }
    today() {
        this.state.weekStart = DateTime.local().startOf("week");
        this.loadData();
    }
    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }
    async onGroupbyChange(ev) {
        const value = ev.target.value;
        this.state.groupbyField = value;
        // Keep the toolbar picker and the Settings screen in sync — both
        // read/write the same ir.config_parameter.
        await this.orm.call("ir.config_parameter", "set_param", [
            "ngyn_calendar_gantt.groupby_field",
            value,
        ]);
        await this.loadData();
    }

    /* =====================================================
       RENDER HELPERS
       ===================================================== */
    get groupbyOptions() {
        return Object.entries(GROUPBY_FIELDS).map(([value, { label }]) => ({ value, label }));
    }
    get timezoneLabel() {
        try {
            return Intl.DateTimeFormat().resolvedOptions().timeZone;
        } catch {
            return "";
        }
    }
    get weekRangeLabel() {
        const start = this.state.weekStart;
        const end = start.plus({ days: 6 });
        return `${start.toFormat("MMM d")} – ${end.toFormat("MMM d, yyyy")}`;
    }
    get dayHeaders() {
        const today = DateTime.local().startOf("day");
        return Array.from({ length: 7 }, (_, i) => {
            const day = this.state.weekStart.plus({ days: i });
            return {
                iso: day.toISODate(),
                label: day.toFormat("ccc d"),
                isToday: day.hasSame(today, "day"),
            };
        });
    }
    get hourTicks() {
        return HOUR_TICKS.map((hour) => ({
            hour,
            label: DateTime.fromObject({ hour }).toFormat("h a"),
            leftPct: ((hour - BUSINESS_START_HOUR) / (BUSINESS_END_HOUR - BUSINESS_START_HOUR)) * 100,
        }));
    }
    get filteredRows() {
        const q = this.state.searchQuery.trim().toLowerCase();
        if (!q) {
            return this.state.rows;
        }
        const result = [];
        for (const row of this.state.rows) {
            const rowMatches = row.label.toLowerCase().includes(q);
            const events = rowMatches ? row.events : row.events.filter((ev) => ev.name.toLowerCase().includes(q));
            if (!events.length) {
                continue;
            }
            result.push({ ...row, events, lanes: packLanes(events) });
        }
        return result;
    }
    barTitle(ev) {
        const installerNames = ev.installers.map((p) => p.name).join(", ");
        const suffix = installerNames ? ` — ${installerNames}` : "";
        return `${ev.name} (${ev.start.toFormat("ccc h:mm a")} – ${ev.stop.toFormat("h:mm a")})${suffix}`;
    }
    barStyle(ev) {
        const weekStart = this.state.weekStart;
        let dayIndex = Math.round(ev.start.startOf("day").diff(weekStart, "days").days);
        dayIndex = Math.min(6, Math.max(0, dayIndex));

        const dayStart = ev.start.startOf("day");
        const startMinRaw = ev.start.diff(dayStart, "minutes").minutes;
        const stopMinRaw = ev.stop.hasSame(ev.start, "day")
            ? ev.stop.diff(dayStart, "minutes").minutes
            : BUSINESS_END_HOUR * 60;

        const clampToWindow = (m) => Math.min(BUSINESS_END_HOUR * 60, Math.max(BUSINESS_START_HOUR * 60, m));
        const startMin = clampToWindow(startMinRaw) - BUSINESS_START_HOUR * 60;
        const stopMin = clampToWindow(stopMinRaw) - BUSINESS_START_HOUR * 60;

        const dayWidthPct = 100 / 7;
        const left = dayIndex * dayWidthPct + (startMin / BUSINESS_WINDOW_MIN) * dayWidthPct;
        const width = Math.max(0.5, ((stopMin - startMin) / BUSINESS_WINDOW_MIN) * dayWidthPct);
        return `left:${left}%; width:${width}%; top:${ev.lane * LANE_HEIGHT}px;`;
    }
    rowHeight(row) {
        return `height:${Math.max(1, row.lanes.length) * LANE_HEIGHT}px;`;
    }
    initials(name) {
        return computeInitials(name);
    }
    avatarColor(id) {
        return computeAvatarColor(id);
    }
    openEvent(ev) {
        this.dialog.add(FormViewDialog, {
            resModel: "calendar.event",
            resId: ev.id,
            title: ev.name,
            onRecordSaved: () => this.loadData(),
        });
    }
}

registry.category("actions").add("ngyn_calendar_gantt.timeline", NgynCalendarGanttTimeline);
