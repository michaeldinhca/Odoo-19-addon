/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps, useExternalListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { serializeDateTime, deserializeDateTime } from "@web/core/l10n/dates";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { WithSearch } from "@web/search/with_search/with_search";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { Domain } from "@web/core/domain";

const { DateTime } = luxon;

/* =========================================================
   Rows are grouped by whichever field the real Odoo Group By
   menu currently has active (driven by <filter> entries in
   views/calendar_event_search_views.xml — adding a third
   grouping option later is purely an XML change). This map is
   this file's own copy of that short list of *supported*
   fields, same hand-rolled-over-generic approach
   ngyn_resource_planning already uses for its own lookups.
   ========================================================= */
const GROUPBY_FIELDS = {
    opportunity_id: { label: "Opportunity", type: "many2one" },
    partner_ids: { label: "Attendee", type: "many2many" },
};
const DEFAULT_GROUPBY = "opportunity_id";
const UNASSIGNED_KEY = "__unassigned__";
const LANE_HEIGHT = 32; // px — must match .o_ngyn_gantt_bar height + gap in the SCSS

// Business-hours window the timeline is scaled to (6am–8pm, not a full 24h
// day). An event outside this window, or spanning past midnight, is visually
// clamped to the nearest edge rather than hidden or breaking the day-column
// math.
const BUSINESS_START_HOUR = 6;
const BUSINESS_END_HOUR = 20;
const BUSINESS_WINDOW_MIN = (BUSINESS_END_HOUR - BUSINESS_START_HOUR) * 60;
const HOUR_TICKS = [6, 9, 12, 15, 18];
const RESIZE_SNAP_MIN = 15;
// Bars render at least this wide (as a % of the whole 7-day grid) so short
// bookings stay legible instead of shrinking to an unreadable sliver — see
// packLanes() for why lane-packing has to know about this floor too, not
// just barStyle().
const MIN_BAR_WIDTH_PCT = 3.5;

const AVATAR_PALETTE = ["#2F5D8A", "#C1611F", "#3D7A5D", "#A87B12", "#6B4C7A", "#2E7A78", "#B5402C", "#55636F"];
function computeInitials(name) {
    const parts = (name || "?").trim().split(/\s+/);
    return ((parts[0][0] || "") + (parts[parts.length - 1][0] || "")).toUpperCase();
}
function computeAvatarColor(id) {
    return AVATAR_PALETTE[id % AVATAR_PALETTE.length];
}
function formatDelta(minutes) {
    const sign = minutes >= 0 ? "+" : "-";
    const abs = Math.round(Math.abs(minutes));
    const h = Math.floor(abs / 60);
    const m = abs % 60;
    if (h && m) return `${sign}${h}h ${m}m`;
    if (h) return `${sign}${h}h`;
    return `${sign}${m}m`;
}

// Pure function: where an event would ideally sit on the grid (as % of the
// whole 7-day width), before any minimum-width floor is applied. Shared by
// the normal render path and the live drag-resize preview, which needs the
// same math for whichever start/stop it's currently previewing.
function idealPosition(start, stop, weekStart) {
    let dayIndex = Math.round(start.startOf("day").diff(weekStart, "days").days);
    dayIndex = Math.min(6, Math.max(0, dayIndex));

    const dayStart = start.startOf("day");
    const startMinRaw = start.diff(dayStart, "minutes").minutes;
    const stopMinRaw = stop.hasSame(start, "day")
        ? stop.diff(dayStart, "minutes").minutes
        : BUSINESS_END_HOUR * 60;

    const clampToWindow = (m) => Math.min(BUSINESS_END_HOUR * 60, Math.max(BUSINESS_START_HOUR * 60, m));
    const startMin = clampToWindow(startMinRaw) - BUSINESS_START_HOUR * 60;
    const stopMin = clampToWindow(stopMinRaw) - BUSINESS_START_HOUR * 60;

    const dayWidthPct = 100 / 7;
    const left = dayIndex * dayWidthPct + (startMin / BUSINESS_WINDOW_MIN) * dayWidthPct;
    const width = ((stopMin - startMin) / BUSINESS_WINDOW_MIN) * dayWidthPct;
    return { left, width };
}

function packLanes(events, weekStart) {
    // Sort by start, then place each event in the first lane whose last
    // event already ends before this one starts, else open a new lane —
    // this is what actually solves the "4-5 things at once" problem.
    // Lane assignment always uses the real start/stop, never the
    // business-hours-clamped display values.
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

    // Second pass, per lane: two events can be correctly placed in the same
    // lane (they don't truly overlap in time) yet still visually collide,
    // because MIN_BAR_WIDTH_PCT can render a short event wider than the real
    // gap to the next one — e.g. a 1-hour booking followed 15 minutes later
    // by another. Walking each lane in start order and never letting a bar
    // start before the previous one's *rendered* right edge guarantees no
    // visual overlap within a lane, while every bar's left edge still
    // reflects its true start time whenever there's room for it to.
    for (const lane of lanes) {
        let prevRight = -Infinity;
        for (const ev of lane) {
            const ideal = idealPosition(ev.start, ev.stop, weekStart);
            const left = Math.max(ideal.left, prevRight);
            const width = Math.max(MIN_BAR_WIDTH_PCT, ideal.width);
            ev.renderLeft = left;
            ev.renderWidth = width;
            prevRight = left + width;
        }
    }
    return lanes;
}

async function resolveViewId(orm, module, name) {
    const [, resId] = await orm.call("ir.model.data", "check_object_reference", [module, name]);
    return resId;
}

/* =========================================================
   Inner component: everything that isn't the search bar itself.
   Receives domain/groupBy/context from the enclosing WithSearch's
   scoped slot as plain props, and reloads whenever they change —
   the same onWillUpdateProps pattern Odoo's own useModel() uses
   (web/static/src/model/model.js).
   ========================================================= */
export class NgynGanttBody extends Component {
    static template = "ngyn_calendar_gantt.Body";
    static props = {
        domain: { type: Array, optional: true },
        groupBy: { type: Array, element: String, optional: true },
        context: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");

        this.state = useState({
            loading: true,
            weekStart: DateTime.local().startOf("week"),
            activeGroupbyField: DEFAULT_GROUPBY,
            rows: [],
            resizing: null,
            crmPopupViewId: null,
        });
        this._suppressClick = false;
        this._lastSearchKey = null;

        onWillStart(async () => {
            this.state.crmPopupViewId = await resolveViewId(
                this.orm,
                "ngyn_calendar_gantt",
                "crm_lead_view_form_popup"
            );
            await this.loadData(this.props);
        });
        onWillUpdateProps((nextProps) => {
            const key = JSON.stringify([nextProps.domain, nextProps.groupBy]);
            if (key === this._lastSearchKey) {
                return;
            }
            return this.loadData(nextProps);
        });

        useExternalListener(window, "mousemove", this.onResizeMove.bind(this));
        useExternalListener(window, "mouseup", this.onResizeEnd.bind(this));
    }

    /* =====================================================
       DATA LOADING
       ===================================================== */
    async loadData(props) {
        this.state.loading = true;
        this._lastSearchKey = JSON.stringify([props.domain, props.groupBy]);

        const field = GROUPBY_FIELDS[(props.groupBy || [])[0]] ? props.groupBy[0] : DEFAULT_GROUPBY;
        this.state.activeGroupbyField = field;

        const weekStart = this.state.weekStart;
        const weekEnd = weekStart.plus({ days: 7 });
        const weekDomain = [
            ["start", "<", serializeDateTime(weekEnd)],
            ["stop", ">", serializeDateTime(weekStart)],
        ];
        const domain = Domain.and([props.domain || [], weekDomain]).toList({});

        const fields = new Set(["name", "start", "stop", field, "partner_ids"]);

        const events = await this.orm.searchRead("calendar.event", domain, [...fields], {
            order: "start asc",
        });

        const partnerIds = [...new Set(events.flatMap((ev) => ev.partner_ids || []))];
        let partnerNames = {};
        if (partnerIds.length) {
            const partners = await this.orm.read("res.partner", partnerIds, ["name"]);
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
            const attendees = (ev.partner_ids || []).map((id) => ({
                id,
                name: partnerNames[id] || `#${id}`,
            }));
            const bar = {
                id: ev.id,
                name: ev.name,
                start: deserializeDateTime(ev.start),
                stop: deserializeDateTime(ev.stop),
                attendees,
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
            row.lanes = packLanes(row.events, weekStart);
        }

        this.state.rows = rows;
        this.state.loading = false;
    }

    /* =====================================================
       NAVIGATION
       ===================================================== */
    prevWeek() {
        this.state.weekStart = this.state.weekStart.minus({ days: 7 });
        this.loadData(this.props);
    }
    nextWeek() {
        this.state.weekStart = this.state.weekStart.plus({ days: 7 });
        this.loadData(this.props);
    }
    today() {
        this.state.weekStart = DateTime.local().startOf("week");
        this.loadData(this.props);
    }

    /* =====================================================
       RENDER HELPERS
       ===================================================== */
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
    showCrmIcon(row) {
        return this.state.activeGroupbyField === "opportunity_id" && row.key !== UNASSIGNED_KEY;
    }
    barTitle(ev) {
        const names = ev.attendees.map((p) => p.name).join(", ");
        const suffix = names ? ` — ${names}` : "";
        return `${ev.name} (${ev.start.toFormat("ccc h:mm a")} – ${ev.stop.toFormat("h:mm a")})${suffix}`;
    }
    barStyle(ev) {
        const r = this.state.resizing;
        if (r && r.eventId === ev.id) {
            // Mid-drag: show the live preview position directly, not the
            // lane-packed one — only one bar is ever being dragged at a
            // time, so there's nothing else in its lane to collide with
            // during the drag itself.
            const ideal = idealPosition(r.previewStart, r.previewStop, this.state.weekStart);
            const width = Math.max(MIN_BAR_WIDTH_PCT, ideal.width);
            return `left:${ideal.left}%; width:${width}%; top:${ev.lane * LANE_HEIGHT}px;`;
        }
        return `left:${ev.renderLeft}%; width:${ev.renderWidth}%; top:${ev.lane * LANE_HEIGHT}px;`;
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

    /* =====================================================
       DRAG-TO-RESIZE
       ===================================================== */
    onResizeStart(mouseEvent, ev, edge) {
        mouseEvent.preventDefault();
        mouseEvent.stopPropagation();
        const trackEl = mouseEvent.currentTarget.closest(".o_ngyn_gantt_track");
        this.state.resizing = {
            eventId: ev.id,
            edge,
            startX: mouseEvent.clientX,
            trackWidth: trackEl.getBoundingClientRect().width,
            originalStart: ev.start,
            originalStop: ev.stop,
            previewStart: ev.start,
            previewStop: ev.stop,
            moved: false,
        };
    }
    onResizeMove(mouseEvent) {
        const r = this.state.resizing;
        if (!r) {
            return;
        }
        const deltaPx = mouseEvent.clientX - r.startX;
        if (Math.abs(deltaPx) > 3) {
            r.moved = true;
        }
        const dayWidthPx = r.trackWidth / 7;
        const minutesPerPx = BUSINESS_WINDOW_MIN / dayWidthPx;
        const deltaMinRaw = deltaPx * minutesPerPx;
        const deltaMin = Math.round(deltaMinRaw / RESIZE_SNAP_MIN) * RESIZE_SNAP_MIN;

        if (r.edge === "stop") {
            const dayEnd = r.originalStart.startOf("day").plus({ hours: BUSINESS_END_HOUR });
            const minStop = r.originalStart.plus({ minutes: RESIZE_SNAP_MIN });
            let newStop = r.originalStop.plus({ minutes: deltaMin });
            if (newStop > dayEnd) newStop = dayEnd;
            if (newStop < minStop) newStop = minStop;
            r.previewStop = newStop;
        } else {
            const dayStart = r.originalStop.startOf("day").plus({ hours: BUSINESS_START_HOUR });
            const maxStart = r.originalStop.minus({ minutes: RESIZE_SNAP_MIN });
            let newStart = r.originalStart.plus({ minutes: deltaMin });
            if (newStart < dayStart) newStart = dayStart;
            if (newStart > maxStart) newStart = maxStart;
            r.previewStart = newStart;
        }
    }
    async onResizeEnd() {
        const r = this.state.resizing;
        if (!r) {
            return;
        }
        this.state.resizing = null;
        if (!r.moved) {
            return;
        }
        this._suppressClick = true;
        await this.orm.write("calendar.event", [r.eventId], {
            start: serializeDateTime(r.previewStart),
            stop: serializeDateTime(r.previewStop),
        });
        await this.loadData(this.props);
    }
    get resizeLabel() {
        const r = this.state.resizing;
        if (!r) {
            return "";
        }
        const boundary = r.edge === "stop" ? r.previewStop : r.previewStart;
        const original = r.edge === "stop" ? r.originalStop : r.originalStart;
        const deltaMin = boundary.diff(original, "minutes").minutes;
        return `${boundary.toFormat("ccc h:mm a")} (${deltaMin === 0 ? "no change" : formatDelta(deltaMin)})`;
    }
    resizingEventId() {
        return this.state.resizing ? this.state.resizing.eventId : null;
    }
    resizeBadgeStyle() {
        return this.state.resizing?.edge === "stop" ? "right:0; left:auto;" : "left:0;";
    }

    /* =====================================================
       DIALOGS
       ===================================================== */
    openEvent(ev) {
        if (this._suppressClick) {
            this._suppressClick = false;
            return;
        }
        this.dialog.add(FormViewDialog, {
            resModel: "calendar.event",
            resId: ev.id,
            title: ev.name,
            onRecordSaved: () => this.loadData(this.props),
        });
    }
    openOpportunity(row) {
        this.dialog.add(FormViewDialog, {
            resModel: "crm.lead",
            resId: row.key,
            viewId: this.state.crmPopupViewId,
            title: row.label,
        });
    }
    get defaultNewEventStart() {
        const now = DateTime.local();
        const weekStart = this.state.weekStart;
        const weekEnd = weekStart.plus({ days: 7 });
        const base = now >= weekStart && now < weekEnd ? now : weekStart;
        return base.set({ hour: 9, minute: 0, second: 0, millisecond: 0 });
    }
    createEvent() {
        const start = this.defaultNewEventStart;
        this.dialog.add(FormViewDialog, {
            resModel: "calendar.event",
            resId: false,
            title: "New Event",
            context: {
                default_start: serializeDateTime(start),
                default_stop: serializeDateTime(start.plus({ hours: 1 })),
            },
            onRecordSaved: () => this.loadData(this.props),
        });
    }
}

/* =========================================================
   Outer component: the registered client action. Its only job
   is resolving our dedicated search view's id once, then handing
   off to WithSearch — which provides the real Filters/Group By/
   Favorites search bar backed by that view's own <filter> entries.
   ========================================================= */
export class NgynCalendarGanttTimeline extends Component {
    static template = "ngyn_calendar_gantt.Timeline";
    static components = { WithSearch, Layout, SearchBar, NgynGanttBody };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({ searchViewId: null });
        onWillStart(async () => {
            this.state.searchViewId = await resolveViewId(
                this.orm,
                "ngyn_calendar_gantt",
                "calendar_event_view_search_gantt"
            );
        });
    }

    get withSearchProps() {
        return {
            resModel: "calendar.event",
            searchViewId: this.state.searchViewId,
            searchMenuTypes: ["filter", "groupBy", "favorite"],
        };
    }
}

registry.category("actions").add("ngyn_calendar_gantt.timeline", NgynCalendarGanttTimeline);
