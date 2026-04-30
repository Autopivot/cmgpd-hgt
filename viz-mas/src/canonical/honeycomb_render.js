// honeycomb_render.js
// =============================================================================
// SVG renderer for the honeycomb cluster layout produced by `cluster_layout.js`.
//
// Layers (back to front):
//   1. hex-cells           one <polygon> per cell
//   2. hex-stripes         striped overlay for outlier cells (posRatio >2σ)
//   3. cluster-borders     dark strokes between hexes of different clusters
//   4. cluster-histograms  small score-gap distribution charts per cluster
//
// Cells dispatch `cell-clicked` and `cell-hovered` CustomEvents on the host
// SVG element with the full cell record as `event.detail`. Subagents D/E/F
// listen for these events.
// =============================================================================

const SVG_NS = 'http://www.w3.org/2000/svg';

// Fixed color stops (do not change without coordinating with other subagents).
// Anchors at ±2 logit-gap units. Per-pair score_gap reaches ±13 but
// cell-mean values concentrate by averaging up to 12 pairs, so most cells
// sit in [−2, +2]; wider anchors washed out the diverging signal.
const COLOR_LOW  = '#993c1d';   // meanScoreGap <= -2
const COLOR_MID  = '#f5f1e8';   // meanScoreGap ~= 0
const COLOR_HIGH = '#0f6e56';   // meanScoreGap >= +2
// Sequential palette (deploy mode, GT-free): low score → high score.
// Anchors at the cell's actual min/max score range (computed per render).
const SEQ_LOW  = '#f1ecdf';
const SEQ_HIGH = '#3a6a8a';
const BORDER_COLOR = '#888780';
const STRIPE_COLOR = '#888780';
const EMPTY_FILL   = '#ffffff';
const EMPTY_STROKE = '#f0efe9';

/**
 * Render the honeycomb layout into an existing SVG element.
 *
 * @param {SVGSVGElement} svgEl   Target <svg>. Will be cleared and rebuilt.
 * @param {object} layout         Output of `buildHoneycomb`.
 * @param {object} [opts]
 * @param {number} [opts.width=800]
 * @param {number} [opts.height=600]
 * @param {number} [opts.marginPx=40]
 */
export function renderHoneycomb(svgEl, layout, opts = {}) {
    const width = opts.width ?? 800;
    const height = opts.height ?? 600;
    const marginPx = opts.marginPx ?? 40;
    const colorBy = opts.colorBy ?? 'gap';
    const showStripes = opts.showStripes ?? (colorBy === 'gap');

    // Sequential mode needs the cohort-local score range to anchor the ramp.
    let scoreMin = 0, scoreMax = 1;
    if (colorBy === 'score') {
        const populated = layout.cells.filter((c) => !c.empty);
        if (populated.length) {
            scoreMin = Infinity; scoreMax = -Infinity;
            for (const c of populated) {
                if (c.meanScore < scoreMin) scoreMin = c.meanScore;
                if (c.meanScore > scoreMax) scoreMax = c.meanScore;
            }
            if (!isFinite(scoreMin) || scoreMax - scoreMin < 1e-6) { scoreMin = 0; scoreMax = 1; }
        }
    }
    function cellFill(cell) {
        if (colorBy === 'score') {
            const t = (cell.meanScore - scoreMin) / (scoreMax - scoreMin);
            return lerpHex(SEQ_LOW, SEQ_HIGH, Math.max(0, Math.min(1, t)));
        }
        return divergingColor(cell.meanScoreGap);
    }

    // ----- Clear existing content -----
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);

    svgEl.setAttribute('width', String(width));
    svgEl.setAttribute('height', String(height));
    svgEl.setAttribute('viewBox', `0 0 ${width} ${height}`);

    // Coordinate transform: layout cells live in [0,1]^2.
    // Center them inside the SVG with `marginPx` padding.
    const innerW = width - 2 * marginPx;
    const innerH = height - 2 * marginPx;
    const scale = Math.min(innerW, innerH);
    const offsetX = marginPx + (innerW - scale) / 2;
    const offsetY = marginPx + (innerH - scale) / 2;
    const project = (x, y) => [offsetX + x * scale, offsetY + y * scale];

    // ----- <defs>: stripe pattern for outlier overlay -----
    const defs = document.createElementNS(SVG_NS, 'defs');
    const pattern = document.createElementNS(SVG_NS, 'pattern');
    pattern.setAttribute('id', 'hc-stripes');
    pattern.setAttribute('patternUnits', 'userSpaceOnUse');
    pattern.setAttribute('width', '4');
    pattern.setAttribute('height', '4');
    pattern.setAttribute('patternTransform', 'rotate(45)');
    const stripeRect = document.createElementNS(SVG_NS, 'rect');
    stripeRect.setAttribute('width', '4');
    stripeRect.setAttribute('height', '4');
    stripeRect.setAttribute('fill', 'transparent');
    pattern.appendChild(stripeRect);
    const stripeLine = document.createElementNS(SVG_NS, 'line');
    stripeLine.setAttribute('x1', '0');
    stripeLine.setAttribute('y1', '0');
    stripeLine.setAttribute('x2', '0');
    stripeLine.setAttribute('y2', '4');
    stripeLine.setAttribute('stroke', STRIPE_COLOR);
    stripeLine.setAttribute('stroke-opacity', '0.6');
    stripeLine.setAttribute('stroke-width', '1.5');
    pattern.appendChild(stripeLine);
    defs.appendChild(pattern);
    svgEl.appendChild(defs);

    // ----- Compute baseline posRatio + std-dev across non-empty cells -----
    const populated = layout.cells.filter((c) => !c.empty);
    let baseline = 0;
    let posStd = 0;
    if (populated.length > 0) {
        let sum = 0;
        for (const c of populated) sum += c.posRatio;
        baseline = sum / populated.length;
        let sqSum = 0;
        for (const c of populated) {
            const d = c.posRatio - baseline;
            sqSum += d * d;
        }
        posStd = Math.sqrt(sqSum / populated.length);
    }
    const stripeThresh = 2 * posStd;

    // ----- Layer 1: hex cells -----
    const gCells = document.createElementNS(SVG_NS, 'g');
    gCells.setAttribute('class', 'hex-cells');

    // Build all polygons in memory, then append in one pass for performance.
    const cellNodes = [];
    for (const cell of layout.cells) {
        const poly = document.createElementNS(SVG_NS, 'polygon');
        poly.setAttribute('class', 'hex-cell');
        poly.setAttribute('data-cell-id', String(cell.id));
        poly.setAttribute('points', cell.vertices.map(([x, y]) => {
            const [px, py] = project(x, y);
            return `${px.toFixed(2)},${py.toFixed(2)}`;
        }).join(' '));

        if (cell.empty) {
            poly.setAttribute('fill', EMPTY_FILL);
            poly.setAttribute('stroke', EMPTY_STROKE);
            poly.setAttribute('stroke-width', '0.5');
        } else {
            poly.setAttribute('fill', cellFill(cell));
            poly.setAttribute('stroke', 'none');
        }

        // Click + hover dispatchers. We close over `cell` so subscribers get
        // the full record without having to look it up again.
        poly.addEventListener('click', () => {
            svgEl.dispatchEvent(new CustomEvent('cell-clicked', { detail: cell }));
        });
        poly.addEventListener('mouseenter', () => {
            svgEl.dispatchEvent(new CustomEvent('cell-hovered', { detail: cell }));
        });

        cellNodes.push(poly);
    }
    for (const n of cellNodes) gCells.appendChild(n);
    svgEl.appendChild(gCells);

    // ----- Layer 2: stripe overlay for outliers -----
    // posRatio is GT-dependent — only meaningful in eval mode.
    const gStripes = document.createElementNS(SVG_NS, 'g');
    gStripes.setAttribute('class', 'hex-stripes');
    if (showStripes && stripeThresh > 0) {
        for (const cell of populated) {
            if (Math.abs(cell.posRatio - baseline) > stripeThresh) {
                const overlay = document.createElementNS(SVG_NS, 'polygon');
                overlay.setAttribute('points', cell.vertices.map(([x, y]) => {
                    const [px, py] = project(x, y);
                    return `${px.toFixed(2)},${py.toFixed(2)}`;
                }).join(' '));
                overlay.setAttribute('fill', 'url(#hc-stripes)');
                overlay.setAttribute('pointer-events', 'none');
                gStripes.appendChild(overlay);
            }
        }
    }
    svgEl.appendChild(gStripes);

    // ----- Layer 3: cluster borders -----
    // For every neighbor pair where clusters differ and both cells are non-
    // empty, draw the shared edge segment (the polygon edge that the two
    // hexes share). We compute the shared edge by intersecting the two
    // vertex sets in screen space.
    const gBorders = document.createElementNS(SVG_NS, 'g');
    gBorders.setAttribute('class', 'cluster-borders');

    const cellById = new Map();
    for (const c of layout.cells) cellById.set(c.id, c);
    const neighbors = layout.meta?.neighbors ?? {};
    const seenPairs = new Set();

    for (const cell of layout.cells) {
        if (cell.empty || cell.cluster === null) continue;
        const ns = neighbors[cell.id] ?? [];
        for (const nid of ns) {
            // Avoid duplicates: only draw each unordered pair once.
            const key = cell.id < nid ? `${cell.id}-${nid}` : `${nid}-${cell.id}`;
            if (seenPairs.has(key)) continue;
            seenPairs.add(key);
            const other = cellById.get(nid);
            if (!other || other.empty || other.cluster === null) continue;
            if (other.cluster === cell.cluster) continue;

            const seg = sharedEdge(cell.vertices, other.vertices);
            if (!seg) continue;
            const [a, b] = seg;
            const [ax, ay] = project(a[0], a[1]);
            const [bx, by] = project(b[0], b[1]);
            const line = document.createElementNS(SVG_NS, 'line');
            line.setAttribute('x1', ax.toFixed(2));
            line.setAttribute('y1', ay.toFixed(2));
            line.setAttribute('x2', bx.toFixed(2));
            line.setAttribute('y2', by.toFixed(2));
            line.setAttribute('stroke', BORDER_COLOR);
            line.setAttribute('stroke-width', '1.5');
            line.setAttribute('stroke-linecap', 'round');
            gBorders.appendChild(line);
        }
    }
    svgEl.appendChild(gBorders);

    // (Layer 4 — per-cluster score-gap mini-histograms — removed by user
    // request: the bars added clutter without adding signal beyond what the
    // diverging cell fill already shows. The cell colors are the
    // distribution.)
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * 3-stop diverging color scale on score-gap value.
 *   v <= -2  →  COLOR_LOW
 *   v ==  0  →  COLOR_MID
 *   v >= +2  →  COLOR_HIGH
 * Linear interpolation in sRGB between adjacent stops.
 */
function divergingColor(v) {
    if (v <= -2) return COLOR_LOW;
    if (v >= 2) return COLOR_HIGH;
    if (v < 0) return lerpHex(COLOR_LOW, COLOR_MID, (v + 2) / 2);   // -2..0 → 0..1
    return lerpHex(COLOR_MID, COLOR_HIGH, v / 2);                    //  0..2 → 0..1
}

function lerpHex(a, b, t) {
    const ar = parseInt(a.slice(1, 3), 16);
    const ag = parseInt(a.slice(3, 5), 16);
    const ab = parseInt(a.slice(5, 7), 16);
    const br = parseInt(b.slice(1, 3), 16);
    const bg = parseInt(b.slice(3, 5), 16);
    const bb = parseInt(b.slice(5, 7), 16);
    const r = Math.round(ar + (br - ar) * t);
    const g = Math.round(ag + (bg - ag) * t);
    const bl = Math.round(ab + (bb - ab) * t);
    return '#' + toHex(r) + toHex(g) + toHex(bl);
}

function toHex(n) {
    const s = n.toString(16);
    return s.length < 2 ? '0' + s : s;
}

/**
 * Find the edge segment (two adjacent vertices) shared between two hexagons.
 * Returns [[x1,y1],[x2,y2]] or null if no shared edge is found.
 *
 * Uses a small epsilon to compare floating-point hex-vertex coordinates.
 */
function sharedEdge(va, vb) {
    const EPS = 1e-6;
    const matched = [];
    for (const a of va) {
        for (const b of vb) {
            if (Math.abs(a[0] - b[0]) < EPS && Math.abs(a[1] - b[1]) < EPS) {
                matched.push(a);
                break;
            }
        }
    }
    if (matched.length >= 2) return [matched[0], matched[1]];
    return null;
}
