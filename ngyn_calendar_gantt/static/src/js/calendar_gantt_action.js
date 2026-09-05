/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { serializeDateTime, deserializeDateTime } from "@web/core/l10n/dates";

const { DateTime } = luxon;

/* =========================================================
   Which calendar.event field rows are grouped by is chosen in
   Calendar > Configuration > Settings (res_config_settings.py,
   ngyn_calendar_gantt.groupby_field). This map is this file's
   copy of that same short list — kept in sync manually, same
   hand-rolled approach ngyn_resource_planning already uses for
   its own small lookups.
   ========================================================= */
const GROUPBY_FIELDS = {
    opportunity_id: { label: "Opportunity", type: "many2one" },
    x_ngyn_installer_ids: { label: "Installer", type: "many2many" },
};
const DEFAULT_GROUPBY = "opportunity_id";
const UNASSIGNED_KEY = "__unassigned__";
const LANE_HEIGHT = 32; // px — must match .o_ngyn_gantt_bar height + gap in the SCSS
const MINUTES_PER_WEEK = 7 * 24 * 60;

function packLanes(events) {
    // Sort by start, then place each event in the first lane whose last
    // event already ends before this one starts, else open a new lane.
    // This is what actually solves the "4-5 things at once" problem — bars
    // that overlap in time are stacked instead of drawn on top of each other.
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
        this.action = useService("action");

        this.state = useState({
            loading: true,
            weekStart: DateTime.local().startOf("week"),
            groupbyField: DEFAULT_GROUPBY,
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

        const events = await this.orm.searchRead(
            "calendar.event",
            [
                ["start", "<", serializeDateTime(weekEnd)],
                ["stop", ">", serializeDateTime(weekStart)],
            ],
            ["name", "start", "stop", field],
            { order: "start asc" }
        );

        let partnerNames = {};
        if (GROUPBY_FIELDS[field].type === "many2many") {
            const ids = [...new Set(events.flatMap((ev) => ev[field] || []))];
            if (ids.length) {
                const partners = await this.orm.read("res.partner", ids, ["name"]);
                partnerNames = Object.fromEntries(partners.map((p) => [p.id, p.name]));
            }
        }

        const groups = new Map();
        const ensureGroup = (key, label) => {
            if (!groups.has(key)) {
                groups.set(key, { key, label, events: [] });
            }
            return groups.get(key);
        };

        for (const ev of events) {
            const bar = {
                id: ev.id,
                name: ev.name,
                start: deserializeDateTime(ev.start),
                stop: deserializeDateTime(ev.stop),
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

    /* =====================================================
       RENDER HELPERS
       ===================================================== */
    get groupbyLabel() {
        return GROUPBY_FIELDS[this.state.groupbyField].label;
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
    barTitle(ev) {
        return `${ev.name} (${ev.start.toFormat("ccc h:mm a")} – ${ev.stop.toFormat("h:mm a")})`;
    }
    barStyle(ev) {
        const startMin = Math.max(0, ev.start.diff(this.state.weekStart, "minutes").minutes);
        const endMin = Math.min(MINUTES_PER_WEEK, ev.stop.diff(this.state.weekStart, "minutes").minutes);
        const left = (startMin / MINUTES_PER_WEEK) * 100;
        const width = Math.max(0.5, ((endMin - startMin) / MINUTES_PER_WEEK) * 100);
        return `left:${left}%; width:${width}%; top:${ev.lane * LANE_HEIGHT}px;`;
    }
    rowHeight(row) {
        return `height:${Math.max(1, row.lanes.length) * LANE_HEIGHT}px;`;
    }
    openEvent(ev) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "calendar.event",
            res_id: ev.id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("ngyn_calendar_gantt.timeline", NgynCalendarGanttTimeline);
