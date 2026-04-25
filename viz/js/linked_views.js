// linked_views.js
// =============================================================================
// Two small SVG strip plots that sit below the honeycomb and react to cell
// hover events:
//
//   1. Score-gap strip  (#lv-svg-gap)        — positives above axis, negatives
//                                              below, ticks at p.score_gap.
//   2. Confusion strip  (#lv-svg-confusion)  — one tick per husband, colored
//                                              by Hungarian outcome.
//
// Public API:
//
//   import { initLinkedViews } from './linked_views.js';
//   initLinkedViews(state);
//
// The function locates the two SVGs, listens for `state-changed` (full re-
// render) and `cell-hovered-state` (highlight-only update), and wires both
// strips to the shared `state` object.
// =============================================================================

const SVG_NS = 'http://www.w3.org/2000/svg';

// ----- Palette (kept consistent with honeycomb_render.js) -----
const COLOR_POS       = '#0f6e56';  // green   — positive / correct
const COLOR_NEG       = '#993c1d';  // red     — negative / wrong-wife
const COLOR_COLLISION = '#ba7517';  // amber   — collision
const COLOR_GREY      = '#888780';  // grey    — default / negative-only
const COLOR_INK       = '#1c1b18';  // ink     — highlight stroke

const GAP_VIEWBOX_W = 800;
const GAP_VIEWBOX_H = 80;
const GAP_LEFT_M    = 40;
const GAP_RIGHT_M   = 40;
const GAP_AXIS_Y    = 40;
const GAP_POS_Y     = 30;
const GAP_NEG_Y     = 50;
const GAP_TICK_LEN  = 8;

const CONF_VIEWBOX_W = 800;
const CONF_VIEWBOX_H = 60;
const CONF_LEFT_M    = 40;
const CONF_RIGHT_M   = 40;
const CONF_TICK_W    = 1.5;
const CONF_TICK_H    = 22;
const CONF_TICK_Y    = 30;
const CONF_HOVER_H   = 36;
const CONF_HOVER_Y   = 16;


// =============================================================================
// Public entry point
// =============================================================================

/**
 * Initialize the linked-views module. Idempotent.
 *
 * @param {object} state  Shared state with `state.cohort`, `state.layout`,
 *                        `state.hoveredCell`.
 */
export function initLinkedViews(state) {
    const gapSvg  = document.getElementById('lv-svg-gap');
    const confSvg = document.getElementById('lv-svg-confusion');
    if (!gapSvg || !confSvg) {
        // Nothing to do if the host page hasn't placed the SVGs yet.
        return;
    }

    // Per-strip render context kept on the SVG element itself, so multiple
    // calls to initLinkedViews don't double-bind listeners.
    gapSvg.__lvCtx  = { tickByPairId: new Map() };
    confSvg.__lvCtx = { tickByHusband: new Map(), husbandToPairId: new Map() };

    const onStateChanged = () => {
        renderGapStrip(gapSvg, state);
        renderConfusionStrip(confSvg, state);
        // Re-apply hover state if any (e.g. state-changed fired but a cell is
        // still hovered).
        applyGapHover(gapSvg, state);
        applyConfusionHover(confSvg, state);
    };

    const onHover = () => {
        applyGapHover(gapSvg, state);
        applyConfusionHover(confSvg, state);
    };

    window.addEventListener('state-changed', onStateChanged);
    window.addEventListener('cell-hovered-state', onHover);

    // Initial render.
    onStateChanged();
}


// =============================================================================
// Helpers
// =============================================================================

function clearSvg(svgEl) {
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
}

function setViewBox(svgEl, w, h) {
    svgEl.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svgEl.setAttribute('preserveAspectRatio', 'none');
}

function makeText(x, y, str, opts = {}) {
    const t = document.createElementNS(SVG_NS, 'text');
    t.setAttribute('x', String(x));
    t.setAttribute('y', String(y));
    t.setAttribute('font-size', String(opts.fontSize ?? 9));
    t.setAttribute('fill', opts.fill ?? 'var(--border)');
    if (opts.anchor) t.setAttribute('text-anchor', opts.anchor);
    t.textContent = str;
    return t;
}

function makeLoading(svgEl, vbW, vbH) {
    clearSvg(svgEl);
    setViewBox(svgEl, vbW, vbH);
    const t = makeText(vbW / 2, vbH / 2, 'Loading…', {
        fontSize: 11,
        anchor: 'middle',
        fill: 'var(--border)',
    });
    t.setAttribute('dominant-baseline', 'middle');
    svgEl.appendChild(t);
}


// =============================================================================
// Strip 1 — score-gap distribution
// =============================================================================

function renderGapStrip(svgEl, state) {
    clearSvg(svgEl);
    setViewBox(svgEl, GAP_VIEWBOX_W, GAP_VIEWBOX_H);
    svgEl.__lvCtx.tickByPairId = new Map();

    const cohort = state.cohort;
    if (!cohort || !Array.isArray(cohort.pairs) || cohort.pairs.length === 0) {
        makeLoading(svgEl, GAP_VIEWBOX_W, GAP_VIEWBOX_H);
        return;
    }

    // ----- Centerline -----
    const axis = document.createElementNS(SVG_NS, 'line');
    axis.setAttribute('x1', String(GAP_LEFT_M));
    axis.setAttribute('x2', String(GAP_VIEWBOX_W - GAP_RIGHT_M));
    axis.setAttribute('y1', String(GAP_AXIS_Y));
    axis.setAttribute('y2', String(GAP_AXIS_Y));
    axis.setAttribute('stroke', 'var(--border)');
    axis.setAttribute('stroke-width', '0.5');
    axis.setAttribute('opacity', '0.6');
    svgEl.appendChild(axis);

    // ----- Labels -----
    svgEl.appendChild(makeText(10, 15, 'positives'));
    svgEl.appendChild(makeText(10, 70, 'negatives'));

    // ----- Determine domain from valid score_gap values -----
    let gMin = Infinity;
    let gMax = -Infinity;
    for (const p of cohort.pairs) {
        const g = p.score_gap;
        if (g == null || Number.isNaN(g)) continue;
        if (g < gMin) gMin = g;
        if (g > gMax) gMax = g;
    }
    if (!isFinite(gMin) || !isFinite(gMax)) {
        // No valid score_gap anywhere — nothing to draw.
        return;
    }
    if (gMin === gMax) {
        // Degenerate: pad a bit so the scale doesn't divide by zero.
        gMin -= 1;
        gMax += 1;
    }

    const pxLo = GAP_LEFT_M;
    const pxHi = GAP_VIEWBOX_W - GAP_RIGHT_M;
    const denom = gMax - gMin;
    const xOf = (g) => pxLo + ((g - gMin) / denom) * (pxHi - pxLo);

    const tickByPairId = svgEl.__lvCtx.tickByPairId;

    // ----- Build all ticks once -----
    // Group container so we can keep DOM tidy.
    const group = document.createElementNS(SVG_NS, 'g');
    group.setAttribute('class', 'gap-ticks');
    svgEl.appendChild(group);

    const half = GAP_TICK_LEN / 2;

    for (const p of cohort.pairs) {
        const g = p.score_gap;
        if (g == null || Number.isNaN(g)) continue;
        const x = xOf(g);
        const yMid = (p.label === 1) ? GAP_POS_Y : GAP_NEG_Y;

        const line = document.createElementNS(SVG_NS, 'line');
        line.setAttribute('x1', String(x));
        line.setAttribute('x2', String(x));
        line.setAttribute('y1', String(yMid - half));
        line.setAttribute('y2', String(yMid + half));
        line.setAttribute('stroke', COLOR_GREY);
        line.setAttribute('stroke-width', '1');
        line.setAttribute('opacity', '0.3');
        // Cache color tier for the hover update so we don't re-decide it.
        line.__lvLabel = p.label;
        group.appendChild(line);
        tickByPairId.set(p.id, line);
    }
}

function applyGapHover(svgEl, state) {
    const ctx = svgEl.__lvCtx;
    if (!ctx || !ctx.tickByPairId) return;
    const tickByPairId = ctx.tickByPairId;

    const hovered = state.hoveredCell;
    const layout = state.layout;
    let pairIds = null;
    if (hovered != null && layout && Array.isArray(layout.cells)) {
        const cell = layout.cells.find(c => c.id === hovered);
        if (cell && Array.isArray(cell.pairIds)) {
            pairIds = new Set(cell.pairIds);
        }
    }

    if (!pairIds) {
        // Restore default styling.
        for (const line of tickByPairId.values()) {
            line.setAttribute('stroke', COLOR_GREY);
            line.setAttribute('stroke-width', '1');
            line.setAttribute('opacity', '0.3');
        }
        return;
    }

    for (const [pid, line] of tickByPairId) {
        if (pairIds.has(pid)) {
            const color = (line.__lvLabel === 1) ? COLOR_POS : COLOR_NEG;
            line.setAttribute('stroke', color);
            line.setAttribute('stroke-width', '2');
            line.setAttribute('opacity', '1');
        } else {
            line.setAttribute('stroke', COLOR_GREY);
            line.setAttribute('stroke-width', '1');
            line.setAttribute('opacity', '0.3');
        }
    }
}


// =============================================================================
// Strip 2 — confusion strip
// =============================================================================

/**
 * Classify a husband's Hungarian outcome.
 * @returns {'correct'|'collision'|'wrong-wife'|'negative-only'}
 */
function classifyHusband(positivePair) {
    if (!positivePair) return 'negative-only';
    if (positivePair.hungarian_correct === true) return 'correct';
    const rank = positivePair.rank_of_true_wife;
    if (rank != null && rank > 1) return 'wrong-wife';
    // Hungarian got it wrong but raw rank was 1 → collision.
    return 'collision';
}

function colorForOutcome(outcome) {
    switch (outcome) {
        case 'correct':       return COLOR_POS;
        case 'collision':     return COLOR_COLLISION;
        case 'wrong-wife':    return COLOR_NEG;
        case 'negative-only': return COLOR_GREY;
        default:              return COLOR_GREY;
    }
}

function renderConfusionStrip(svgEl, state) {
    clearSvg(svgEl);
    setViewBox(svgEl, CONF_VIEWBOX_W, CONF_VIEWBOX_H);
    svgEl.__lvCtx.tickByHusband = new Map();
    svgEl.__lvCtx.husbandToPairId = new Map();

    const cohort = state.cohort;
    if (!cohort || !Array.isArray(cohort.pairs) || cohort.pairs.length === 0) {
        makeLoading(svgEl, CONF_VIEWBOX_W, CONF_VIEWBOX_H);
        return;
    }

    // ----- Group pairs by husband; pick the (single) positive if present. -----
    const positiveByHusband = new Map();   // husband_id -> positive pair
    const husbandsSeen = new Set();
    for (const p of cohort.pairs) {
        if (!p || p.husband_id == null) continue;
        husbandsSeen.add(p.husband_id);
        if (p.label === 1 && !positiveByHusband.has(p.husband_id)) {
            positiveByHusband.set(p.husband_id, p);
        }
    }

    const husbands = Array.from(husbandsSeen).sort();
    if (husbands.length === 0) return;

    // ----- x positions: spread across [40, 760]. -----
    const pxLo = CONF_LEFT_M;
    const pxHi = CONF_VIEWBOX_W - CONF_RIGHT_M;
    const span = pxHi - pxLo;
    const n = husbands.length;
    const xOf = (i) => (n === 1) ? (pxLo + span / 2) : (pxLo + (i / (n - 1)) * span);

    // ----- Build all ticks once -----
    const group = document.createElementNS(SVG_NS, 'g');
    group.setAttribute('class', 'conf-ticks');
    svgEl.appendChild(group);

    const tickByHusband = svgEl.__lvCtx.tickByHusband;
    const husbandToPairId = svgEl.__lvCtx.husbandToPairId;

    for (let i = 0; i < n; i++) {
        const hid = husbands[i];
        const positive = positiveByHusband.get(hid) || null;
        const outcome = classifyHusband(positive);
        const fill = colorForOutcome(outcome);

        const x = xOf(i);
        const rect = document.createElementNS(SVG_NS, 'rect');
        rect.setAttribute('x', String(x - CONF_TICK_W / 2));
        rect.setAttribute('y', String(CONF_TICK_Y));
        rect.setAttribute('width', String(CONF_TICK_W));
        rect.setAttribute('height', String(CONF_TICK_H));
        rect.setAttribute('fill', fill);
        rect.setAttribute('opacity', '1');
        rect.__lvOutcome = outcome;
        group.appendChild(rect);

        tickByHusband.set(hid, rect);
        if (positive) husbandToPairId.set(hid, positive.id);
    }

    // ----- Legend (right side) -----
    renderConfusionLegend(svgEl);
}

function renderConfusionLegend(svgEl) {
    const legend = document.createElementNS(SVG_NS, 'g');
    legend.setAttribute('class', 'conf-legend');

    const items = [
        { color: COLOR_POS,       label: 'correct' },
        { color: COLOR_COLLISION, label: 'collision' },
        { color: COLOR_NEG,       label: 'wrong wife' },
        { color: COLOR_GREY,      label: 'negative only' },
    ];

    let x = 600;
    const y = 10;
    const swatchW = 8;
    const swatchH = 8;
    const gap = 4;

    for (const item of items) {
        const sw = document.createElementNS(SVG_NS, 'rect');
        sw.setAttribute('x', String(x));
        sw.setAttribute('y', String(y));
        sw.setAttribute('width', String(swatchW));
        sw.setAttribute('height', String(swatchH));
        sw.setAttribute('fill', item.color);
        legend.appendChild(sw);

        const tx = x + swatchW + gap;
        const t = makeText(tx, y + swatchH - 1, item.label, { fontSize: 9 });
        legend.appendChild(t);

        // Roughly estimate label width: 5 px per char. Keeps the four labels
        // packed inside the [600, 780] band.
        x = tx + item.label.length * 5 + 8;
    }

    svgEl.appendChild(legend);
}

function applyConfusionHover(svgEl, state) {
    const ctx = svgEl.__lvCtx;
    if (!ctx || !ctx.tickByHusband) return;
    const tickByHusband = ctx.tickByHusband;
    const husbandToPairId = ctx.husbandToPairId;

    const hovered = state.hoveredCell;
    const layout = state.layout;
    let pairIds = null;
    if (hovered != null && layout && Array.isArray(layout.cells)) {
        const cell = layout.cells.find(c => c.id === hovered);
        if (cell && Array.isArray(cell.pairIds)) {
            pairIds = new Set(cell.pairIds);
        }
    }

    if (!pairIds) {
        // Restore default state.
        for (const rect of tickByHusband.values()) {
            rect.setAttribute('y', String(CONF_TICK_Y));
            rect.setAttribute('height', String(CONF_TICK_H));
            rect.setAttribute('opacity', '1');
            rect.removeAttribute('stroke');
            rect.removeAttribute('stroke-width');
        }
        return;
    }

    for (const [hid, rect] of tickByHusband) {
        const pid = husbandToPairId.get(hid);
        const isHit = (pid != null) && pairIds.has(pid);
        if (isHit) {
            rect.setAttribute('y', String(CONF_HOVER_Y));
            rect.setAttribute('height', String(CONF_HOVER_H));
            rect.setAttribute('opacity', '1');
            rect.setAttribute('stroke', COLOR_INK);
            rect.setAttribute('stroke-width', '1');
        } else {
            rect.setAttribute('y', String(CONF_TICK_Y));
            rect.setAttribute('height', String(CONF_TICK_H));
            rect.setAttribute('opacity', '0.4');
            rect.removeAttribute('stroke');
            rect.removeAttribute('stroke-width');
        }
    }
}
