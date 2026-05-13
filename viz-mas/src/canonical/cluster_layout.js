// cluster_layout.js
// =============================================================================
// ASight-style honeycomb packing for HGT cohort embeddings.
//
// Given a cohort JSON (with mds_coords + clusters), this module produces a
// hex-grid layout where every point is assigned to a hex cell, hexes contain
// only same-cluster points (subject to capacity), and points are pulled
// inward toward their cluster centroid using an iterative attraction step.
//
// The output is consumed by `honeycomb_render.js` and downstream UI modules
// (Subagents D/E/F) which listen for cell-click / cell-hover events.
// =============================================================================

/**
 * Build a honeycomb layout from a cohort JSON.
 *
 * @param {object} cohort        Loaded cohort JSON (see schema in build doc).
 * @param {object} [opts]        Layout options.
 * @param {number} [opts.hexRadius=0.04]  Hex circumradius in normalized [0,1] units.
 * @param {number} [opts.capacity=12]     Max points per hex cell.
 * @returns {object} layout      { cells, clusters, meta }
 */
export function buildHoneycomb(cohort, opts = {}) {
    const hexRadius = opts.hexRadius ?? 0.04;
    const capacity = opts.capacity ?? 12;

    const pairs = cohort.pairs || [];
    const mds = cohort.mds_coords || [];
    const clusterAssign = cohort.clusters || [];
    const n = pairs.length;

    // ---------------------------------------------------------------------
    // 1. Normalize MDS coordinates to [0,1]^2 using 2nd–98th percentile
    //    bounds. MDS routinely produces a few extreme outliers that stretch
    //    min/max by 3–5×, compressing 90% of pairs into a small visual area.
    //    Percentile clipping keeps the honeycomb coordinate frame consistent
    //    with HexEmbeddingView's scatter mode (which also uses 2nd–98th
    //    bounds), so the training-reference heatmap aligns across all modes.
    // ---------------------------------------------------------------------
    const norm = new Array(n);
    if (n > 0) {
        const xs = new Array(n), ys = new Array(n);
        for (let i = 0; i < n; i++) {
            const c = mds[i] || [0, 0];
            xs[i] = c[0]; ys[i] = c[1];
        }
        xs.sort((a, b) => a - b); ys.sort((a, b) => a - b);
        const pct = (arr, p) => arr[Math.max(0, Math.min(arr.length - 1, Math.round((arr.length - 1) * p / 100)))];
        const xMin = pct(xs, 2), xMax = pct(xs, 98);
        const yMin = pct(ys, 2), yMax = pct(ys, 98);
        const xRange = (xMax - xMin) || 1;
        const yRange = (yMax - yMin) || 1;
        for (let i = 0; i < n; i++) {
            const c = mds[i] || [0, 0];
            norm[i] = [
                Math.max(0, Math.min(1, (c[0] - xMin) / xRange)),
                Math.max(0, Math.min(1, (c[1] - yMin) / yRange)),
            ];
        }
    }

    // ---------------------------------------------------------------------
    // 2. Compute cluster centroids in normalized space.
    // ---------------------------------------------------------------------
    const k = cohort.k_clusters ?? (clusterAssign.length ? Math.max(...clusterAssign) + 1 : 1);
    const centroidSums = new Array(k).fill(null).map(() => [0, 0, 0]);
    for (let i = 0; i < n; i++) {
        const cl = clusterAssign[i] ?? 0;
        if (cl < 0 || cl >= k) continue;
        centroidSums[cl][0] += norm[i][0];
        centroidSums[cl][1] += norm[i][1];
        centroidSums[cl][2] += 1;
    }
    const centroids = centroidSums.map((s) => (s[2] > 0 ? [s[0] / s[2], s[1] / s[2]] : [0.5, 0.5]));

    // ---------------------------------------------------------------------
    // 3. Generate a flat-top hex grid covering [0,1]^2.
    //    Flat-top: width = 2R, height = sqrt(3)*R.
    //    Column step = 1.5*R, row step = sqrt(3)*R, with row offset every other column.
    // ---------------------------------------------------------------------
    const R = hexRadius;
    const sqrt3 = Math.sqrt(3);
    const colStep = 1.5 * R;
    const rowStep = sqrt3 * R;

    const cells = [];
    // Generate enough columns/rows to cover [0,1]^2 with margin.
    const nCols = Math.ceil(1 / colStep) + 2;
    const nRows = Math.ceil(1 / rowStep) + 2;

    let cellId = 0;
    for (let q = -1; q < nCols; q++) {
        for (let r = -1; r < nRows; r++) {
            const cx = q * colStep;
            const cy = r * rowStep + ((q & 1) ? rowStep / 2 : 0);
            // Skip cells fully outside [0,1]^2 (with one-radius margin so we keep edges).
            if (cx < -R || cx > 1 + R || cy < -R || cy > 1 + R) continue;
            cells.push({
                id: cellId++,
                q, r,
                cx, cy,
                vertices: hexVertices(cx, cy, R, /*flatTop=*/true),
                capacity,
                occupants: [],
                cluster: null,
            });
        }
    }

    // Build a fast cell lookup by axial coords for neighbor queries later.
    const cellByQR = new Map();
    for (const c of cells) cellByQR.set(qrKey(c.q, c.r), c);

    // ---------------------------------------------------------------------
    // 4. Sort points by distance to their cluster centroid (closest first).
    //    Closest-first ordering means the densest core of each cluster claims
    //    the central hexes; outliers spiral outward.
    // ---------------------------------------------------------------------
    const order = new Array(n);
    for (let i = 0; i < n; i++) order[i] = i;
    order.sort((a, b) => {
        const ca = centroids[clusterAssign[a] ?? 0];
        const cb = centroids[clusterAssign[b] ?? 0];
        const da = dist2(norm[a], ca);
        const db = dist2(norm[b], cb);
        return da - db;
    });

    // ---------------------------------------------------------------------
    // 5. Iteratively pack points. For each point:
    //      - take a half-step toward its cluster centroid,
    //      - find the nearest hex (linear scan; ncells is small),
    //      - if that hex has room and matches the cluster, drop it in,
    //      - otherwise step further toward centroid; if still no luck,
    //        push outward by 2R from the centroid until a free hex is found.
    // ---------------------------------------------------------------------
    const MAX_INWARD = 50;
    const MAX_OUTWARD = 200;

    for (const pi of order) {
        const cl = clusterAssign[pi] ?? 0;
        const centroid = centroids[cl];
        let pos = [norm[pi][0], norm[pi][1]];
        let placed = false;

        // ---- inward attraction loop ----
        for (let it = 0; it < MAX_INWARD; it++) {
            // Halfway step toward centroid (geometric series; each iter halves the gap).
            pos = [(pos[0] + centroid[0]) * 0.5, (pos[1] + centroid[1]) * 0.5];
            const cell = nearestCell(cells, pos);
            if (!cell) break;
            if (cell.occupants.length < cell.capacity &&
                (cell.cluster === null || cell.cluster === cl)) {
                cell.occupants.push(pi);
                cell.cluster = cl;
                placed = true;
                break;
            }
            // Otherwise: continue to next iteration; pos collapses toward centroid.
        }

        if (placed) continue;

        // ---- outward radial fallback ----
        // Start from centroid and push outward at random angles until a free
        // same-cluster (or empty) cell appears.
        let radius = 2 * R;
        let angle = Math.random() * Math.PI * 2;
        for (let it = 0; it < MAX_OUTWARD; it++) {
            const px = centroid[0] + radius * Math.cos(angle);
            const py = centroid[1] + radius * Math.sin(angle);
            const cell = nearestCell(cells, [px, py]);
            if (cell &&
                cell.occupants.length < cell.capacity &&
                (cell.cluster === null || cell.cluster === cl)) {
                cell.occupants.push(pi);
                cell.cluster = cl;
                placed = true;
                break;
            }
            // Spiral outward: rotate angle, grow radius slowly.
            angle += 0.7;
            if ((it & 7) === 7) radius += 2 * R;
        }

        if (!placed) {
            // Last-resort: drop into any empty cell (should be rare).
            for (const c of cells) {
                if (c.occupants.length < c.capacity && (c.cluster === null || c.cluster === cl)) {
                    c.occupants.push(pi);
                    c.cluster = cl;
                    placed = true;
                    break;
                }
            }
        }
    }

    // ---------------------------------------------------------------------
    // 6. Compute per-cell aggregates and build output records.
    // ---------------------------------------------------------------------
    const outCells = [];
    for (const c of cells) {
        if (c.occupants.length === 0) {
            // Keep empty cells in the output so the grid renders fully.
            outCells.push({
                id: c.id,
                cx: c.cx, cy: c.cy,
                vertices: c.vertices,
                cluster: null,
                pairIds: [],
                meanScoreGap: 0,
                posRatio: 0,
                patriPathMean: 0,
                sameLinFrac: 0,
                confMean: 0,
                empty: true,
            });
            continue;
        }
        let sumGap = 0, sumPos = 0, sumPatri = 0, sumSame = 0;
        for (const pi of c.occupants) {
            const p = pairs[pi] || {};
            sumGap += p.score_gap ?? 0;
            sumPos += (p.label === 1) ? 1 : 0;
            sumPatri += p.patri_path_count ?? 0;
            sumSame += p.same_lineage ? 1 : 0;
        }
        const nOcc = c.occupants.length;
        outCells.push({
            id: c.id,
            cx: c.cx, cy: c.cy,
            vertices: c.vertices,
            cluster: c.cluster,
            pairIds: c.occupants.slice(),
            meanScoreGap: sumGap / nOcc,
            posRatio: sumPos / nOcc,
            patriPathMean: sumPatri / nOcc,
            sameLinFrac: sumSame / nOcc,
            confMean: sumGap / nOcc,
            empty: false,
        });
    }

    // ---------------------------------------------------------------------
    // 7. Build cluster summaries.
    // ---------------------------------------------------------------------
    const clustersOut = [];
    for (let i = 0; i < k; i++) {
        const cellIds = [];
        let total = 0;
        for (const oc of outCells) {
            if (oc.cluster === i) {
                cellIds.push(oc.id);
                total += oc.pairIds.length;
            }
        }
        clustersOut.push({
            id: i,
            centroidX: centroids[i][0],
            centroidY: centroids[i][1],
            cellIds,
            n: total,
        });
    }

    return {
        cells: outCells,
        clusters: clustersOut,
        meta: {
            n_pairs: n,
            hexRadius,
            capacity,
            nCells: outCells.length,
            // Pre-compute neighbor adjacency keyed by cell id, so the renderer
            // can draw cluster-borders without recomputing axial offsets.
            neighbors: buildNeighborMap(cells, cellByQR),
        },
    };
}

// ============================================================================
// Helpers
// ============================================================================

function qrKey(q, r) { return q + ',' + r; }

function dist2(a, b) {
    const dx = a[0] - b[0];
    const dy = a[1] - b[1];
    return dx * dx + dy * dy;
}

/**
 * Linear nearest-cell scan. cells.length is small (typically <500 for hexRadius=0.04
 * over [0,1]^2), so a flat scan is faster than a KDTree once you account for
 * tree-build overhead.
 */
function nearestCell(cells, pos) {
    let best = null;
    let bestD = Infinity;
    for (const c of cells) {
        const d = dist2(pos, [c.cx, c.cy]);
        if (d < bestD) {
            bestD = d;
            best = c;
        }
    }
    return best;
}

/**
 * Compute the 6 vertices of a hexagon centered at (cx, cy).
 * flatTop=true: vertices at angles 0, 60, 120, ... degrees (flat side on top/bottom).
 */
function hexVertices(cx, cy, R, flatTop) {
    const verts = new Array(6);
    const offset = flatTop ? 0 : Math.PI / 6;
    for (let i = 0; i < 6; i++) {
        const a = offset + i * Math.PI / 3;
        verts[i] = [cx + R * Math.cos(a), cy + R * Math.sin(a)];
    }
    return verts;
}

/**
 * For each cell id, compute the list of neighboring cell ids using axial-
 * coordinate offsets for an offset-column flat-top grid.
 *
 * We store the result as { [cellId]: [neighborId, ...] } so the renderer can
 * iterate neighbor pairs once when drawing cluster borders.
 */
function buildNeighborMap(cells, cellByQR) {
    const map = {};
    for (const c of cells) {
        const ns = [];
        // Flat-top, offset-by-column ("odd-q") neighbor offsets.
        // Different deltas for even/odd columns.
        const evenCol = (c.q & 1) === 0;
        const deltas = evenCol
            ? [[+1, 0], [+1, -1], [0, -1], [-1, -1], [-1, 0], [0, +1]]
            : [[+1, +1], [+1, 0], [0, -1], [-1, 0], [-1, +1], [0, +1]];
        for (const [dq, dr] of deltas) {
            const n = cellByQR.get(qrKey(c.q + dq, c.r + dr));
            if (n) ns.push(n.id);
        }
        map[c.id] = ns;
    }
    return map;
}
