// contour_render.js
// Subagent C: contour-overlay layer for the HGT marriage-edge viewer.
// Computes a smoothed scalar field from per-cell aggregates and renders
// percentile-based isolines via d3-contour, colored by leading channel.
//
// Public API:
//   renderContours(svgEl, layout, weights, stride, opts)
//
// Pure ES module; depends on d3-contour loaded globally as window.d3.

const SVG_NS = "http://www.w3.org/2000/svg";

// Fixed channel palette (do not change).
const CHANNEL_COLORS = {
  confidence: "#1d9e75",   // teal
  patrilineal: "#ba7517",  // amber
  endogamy: "#7f77dd",     // purple
};
const CHANNEL_NAMES = ["confidence", "patrilineal", "endogamy"];

// Cached scaffolding so repeated slider invocations are cheap.
let _scaffold = null;

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function _ensureD3() {
  if (typeof window === "undefined" || !window.d3 || typeof window.d3.contours !== "function") {
    throw new Error(
      "contour_render: window.d3.contours is not available. " +
      "Ensure d3-contour is loaded via the CDN script before importing this module."
    );
  }
  return window.d3;
}

function _normalize(values) {
  // Map an array of finite numbers to [0,1]. NaNs become 0.
  let lo = +Infinity, hi = -Infinity;
  for (const v of values) {
    if (Number.isFinite(v)) {
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi - lo < 1e-12) {
    return values.map(() => 0);
  }
  const span = hi - lo;
  return values.map((v) => (Number.isFinite(v) ? (v - lo) / span : 0));
}

function _percentile(sortedAsc, p) {
  // p in [0,100]; sortedAsc must be ascending.
  if (sortedAsc.length === 0) return 0;
  if (sortedAsc.length === 1) return sortedAsc[0];
  const idx = (p / 100) * (sortedAsc.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return sortedAsc[lo];
  const frac = idx - lo;
  return sortedAsc[lo] * (1 - frac) + sortedAsc[hi] * frac;
}

function _signedArea(ring) {
  // ring: [[x,y], ...] with first==last typical for d3-contour rings.
  let a = 0;
  for (let i = 0, n = ring.length - 1; i < n; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    a += x1 * y2 - x2 * y1;
  }
  return a / 2;
}

function _ringBoundsCentroid(ring) {
  let xmin = +Infinity, ymin = +Infinity, xmax = -Infinity, ymax = -Infinity;
  for (const [x, y] of ring) {
    if (x < xmin) xmin = x;
    if (y < ymin) ymin = y;
    if (x > xmax) xmax = x;
    if (y > ymax) ymax = y;
  }
  return {
    cx: (xmin + xmax) / 2,
    cy: (ymin + ymax) / 2,
    xmin, ymin, xmax, ymax,
  };
}

function _ringToPath(ring, gridToSvg) {
  // ring is [[gx,gy], ...]; convert to SVG-space path string.
  let s = "";
  for (let i = 0; i < ring.length; i++) {
    const [gx, gy] = ring[i];
    const [px, py] = gridToSvg(gx, gy);
    s += (i === 0 ? "M" : "L") + px.toFixed(2) + "," + py.toFixed(2);
  }
  s += "Z";
  return s;
}

// -----------------------------------------------------------------------------
// Per-cell channel cache
// -----------------------------------------------------------------------------

// We attach a hidden symbol to the layout object so repeated calls reuse the
// computed channel values without disturbing the layout surface API.
const CHANNEL_CACHE_KEY = "__contourChannelCache__";

function _computeChannels(layout) {
  if (layout && layout[CHANNEL_CACHE_KEY]) {
    return layout[CHANNEL_CACHE_KEY];
  }
  const cells = (layout && layout.cells) || [];
  const filled = cells.filter(
    (c) => c && c.pairIds && c.pairIds.length > 0 && Number.isFinite(c.cx) && Number.isFinite(c.cy)
  );

  const confRaw = filled.map((c) =>
    Number.isFinite(c.confMean) ? c.confMean :
    (Number.isFinite(c.meanScoreGap) ? c.meanScoreGap : 0)
  );
  const patriRaw = filled.map((c) => (Number.isFinite(c.patriPathMean) ? c.patriPathMean : 0));
  const endogRaw = filled.map((c) => {
    const v = Number.isFinite(c.sameLinFrac) ? c.sameLinFrac : 0;
    return Math.max(0, Math.min(1, v));
  });

  const conf = _normalize(confRaw);
  const patri = _normalize(patriRaw);
  // endog is already in [0,1] per spec.
  const endog = endogRaw;

  // Estimate hex radius for empty-region cutoff. Use median nearest-neighbor
  // distance / sqrt(3) as a robust proxy if vertices aren't trustworthy.
  let hexRadius = 0;
  if (filled.length > 1) {
    // Try vertices first.
    const sample = filled[0];
    if (sample.vertices && sample.vertices.length >= 2) {
      const [vx, vy] = sample.vertices[0];
      const dx = vx - sample.cx, dy = vy - sample.cy;
      const r = Math.sqrt(dx * dx + dy * dy);
      if (Number.isFinite(r) && r > 0) hexRadius = r;
    }
    if (hexRadius <= 0) {
      // Fallback: nearest-neighbor median.
      const dists = [];
      const N = Math.min(filled.length, 60);
      for (let i = 0; i < N; i++) {
        let best = +Infinity;
        for (let j = 0; j < filled.length; j++) {
          if (i === j) continue;
          const dx = filled[i].cx - filled[j].cx;
          const dy = filled[i].cy - filled[j].cy;
          const d2 = dx * dx + dy * dy;
          if (d2 < best) best = d2;
        }
        if (Number.isFinite(best)) dists.push(Math.sqrt(best));
      }
      dists.sort((a, b) => a - b);
      hexRadius = dists.length ? dists[Math.floor(dists.length / 2)] / Math.sqrt(3) : 1;
    }
  } else if (filled.length === 1 && filled[0].vertices && filled[0].vertices.length >= 1) {
    const [vx, vy] = filled[0].vertices[0];
    const dx = vx - filled[0].cx, dy = vy - filled[0].cy;
    hexRadius = Math.sqrt(dx * dx + dy * dy) || 1;
  } else {
    hexRadius = 1;
  }

  const cache = {
    cells: filled.map((c, i) => ({
      cx: c.cx,
      cy: c.cy,
      conf: conf[i],
      patri: patri[i],
      endog: endog[i],
    })),
    hexRadius,
  };
  try {
    Object.defineProperty(layout, CHANNEL_CACHE_KEY, {
      value: cache,
      enumerable: false,
      configurable: true,
      writable: true,
    });
  } catch (_e) {
    layout[CHANNEL_CACHE_KEY] = cache;
  }
  return cache;
}

// -----------------------------------------------------------------------------
// Scaffolding (grid + cell-pixel coordinates)
// -----------------------------------------------------------------------------

function _buildScaffold(width, height, marginPx, channelCells) {
  const innerW = Math.max(1, width - 2 * marginPx);
  const innerH = Math.max(1, height - 2 * marginPx);

  // Choose grid resolution roughly proportional to inner aspect.
  // Target ~120 wide, scale height by aspect.
  const gridW = 120;
  const gridH = Math.max(20, Math.round((gridW * innerH) / innerW));

  // Cells are in some absolute coordinate system. We need to map cell pixel
  // coords (cx, cy) into our grid index space, and grid index space back to
  // SVG pixel space.
  //
  // Determine the bounding box of cells (assume layout already lays them in a
  // consistent coordinate system — typically it's already SVG pixel coords).
  let xmin = +Infinity, ymin = +Infinity, xmax = -Infinity, ymax = -Infinity;
  for (const c of channelCells) {
    if (c.cx < xmin) xmin = c.cx;
    if (c.cy < ymin) ymin = c.cy;
    if (c.cx > xmax) xmax = c.cx;
    if (c.cy > ymax) ymax = c.cy;
  }
  if (!Number.isFinite(xmin)) {
    xmin = marginPx; ymin = marginPx; xmax = width - marginPx; ymax = height - marginPx;
  }
  // Pad a bit so contours don't get clipped.
  const padX = Math.max(1, (xmax - xmin) * 0.04);
  const padY = Math.max(1, (ymax - ymin) * 0.04);
  xmin -= padX; ymin -= padY; xmax += padX; ymax += padY;
  if (xmax - xmin < 1e-6) { xmax = xmin + 1; }
  if (ymax - ymin < 1e-6) { ymax = ymin + 1; }

  // Map a cell's (cx, cy) into a fractional grid position [0,gridW]×[0,gridH].
  const cellToGrid = (cx, cy) => {
    const u = (cx - xmin) / (xmax - xmin);
    const v = (cy - ymin) / (ymax - ymin);
    return [u * (gridW - 1), v * (gridH - 1)];
  };

  // Map a (gx, gy) grid coord back to SVG pixel space.
  // The cells already live in pixel space, so we map back to that same pixel
  // space (which the SVG itself uses).
  const gridToSvg = (gx, gy) => {
    const u = gx / (gridW - 1);
    const v = gy / (gridH - 1);
    return [xmin + u * (xmax - xmin), ymin + v * (ymax - ymin)];
  };

  // Precompute cell positions in grid space.
  const cellGrid = channelCells.map((c) => {
    const [gx, gy] = cellToGrid(c.cx, c.cy);
    return { gx, gy, cx: c.cx, cy: c.cy };
  });

  return {
    width, height, marginPx,
    gridW, gridH,
    bbox: { xmin, ymin, xmax, ymax },
    cellToGrid, gridToSvg,
    cellGrid,
  };
}

function _scaffoldKey(width, height, marginPx, n) {
  return width + "x" + height + "@" + marginPx + "#" + n;
}

// -----------------------------------------------------------------------------
// IDW rasterization
// -----------------------------------------------------------------------------

function _rasterize(scaffold, channelCells, weights, hexRadius) {
  const { gridW, gridH, cellGrid } = scaffold;
  const N = cellGrid.length;

  // Cell heights & leading channel under current weights.
  const wConf = weights && Number.isFinite(weights.confidence) ? weights.confidence : 1;
  const wPatri = weights && Number.isFinite(weights.patrilineal) ? weights.patrilineal : 1;
  const wEndog = weights && Number.isFinite(weights.endogamy) ? weights.endogamy : 1;

  const cellH = new Float32Array(N);
  const cellLead = new Int8Array(N); // 0=conf, 1=patri, 2=endog
  for (let i = 0; i < N; i++) {
    const c = channelCells[i];
    const a = wConf * c.conf;
    const b = wPatri * c.patri;
    const d = wEndog * c.endog;
    let h = a, lead = 0;
    if (b > h) { h = b; lead = 1; }
    if (d > h) { h = d; lead = 2; }
    cellH[i] = h;
    cellLead[i] = lead;
  }

  const heightField = new Float32Array(gridW * gridH);
  const leadField = new Int8Array(gridW * gridH);

  // Cutoff: grid points with no cell within 3*hexRadius (in pixel units) → 0.
  // Convert hexRadius to grid units using bbox.
  const { bbox } = scaffold;
  const pxPerGridX = (bbox.xmax - bbox.xmin) / Math.max(1, gridW - 1);
  const pxPerGridY = (bbox.ymax - bbox.ymin) / Math.max(1, gridH - 1);
  const avgPxPerGrid = 0.5 * (pxPerGridX + pxPerGridY);
  const cutoffGrid = Math.max(2, (3 * hexRadius) / Math.max(1e-6, avgPxPerGrid));
  const cutoffGrid2 = cutoffGrid * cutoffGrid;

  const K = Math.min(12, N);
  const p = 2;
  const eps = 1e-6;

  // Reusable buffers for K-nearest selection.
  const kIdx = new Int32Array(K);
  const kD2 = new Float64Array(K);

  for (let gy = 0; gy < gridH; gy++) {
    for (let gx = 0; gx < gridW; gx++) {
      // Find K nearest cells (linear scan; N is small, ~200-400).
      let kCount = 0;
      let worstD2 = +Infinity;
      let worstSlot = -1;
      // Also track the nearest distance for cutoff.
      let nearest2 = +Infinity;

      for (let i = 0; i < N; i++) {
        const dx = cellGrid[i].gx - gx;
        const dy = cellGrid[i].gy - gy;
        const d2 = dx * dx + dy * dy;
        if (d2 < nearest2) nearest2 = d2;

        if (kCount < K) {
          kIdx[kCount] = i;
          kD2[kCount] = d2;
          kCount++;
          if (kCount === K) {
            // Find worst slot.
            worstD2 = -Infinity; worstSlot = -1;
            for (let j = 0; j < K; j++) {
              if (kD2[j] > worstD2) { worstD2 = kD2[j]; worstSlot = j; }
            }
          }
        } else if (d2 < worstD2) {
          kIdx[worstSlot] = i;
          kD2[worstSlot] = d2;
          // Recompute worst.
          worstD2 = -Infinity; worstSlot = -1;
          for (let j = 0; j < K; j++) {
            if (kD2[j] > worstD2) { worstD2 = kD2[j]; worstSlot = j; }
          }
        }
      }

      const flat = gy * gridW + gx;

      if (nearest2 > cutoffGrid2) {
        heightField[flat] = 0;
        leadField[flat] = 0;
        continue;
      }

      // IDW weighted sum.
      let wsum = 0, hsum = 0;
      const voteW = [0, 0, 0];
      for (let j = 0; j < kCount; j++) {
        const idx = kIdx[j];
        const d2 = kD2[j];
        // Use Euclidean distance^p with p=2.
        const w = 1 / (d2 + eps);
        wsum += w;
        hsum += w * cellH[idx];
        voteW[cellLead[idx]] += w;
      }
      heightField[flat] = wsum > 0 ? (hsum / wsum) : 0;
      // Modal leading channel (weighted vote).
      let bestC = 0, bestW = voteW[0];
      if (voteW[1] > bestW) { bestC = 1; bestW = voteW[1]; }
      if (voteW[2] > bestW) { bestC = 2; bestW = voteW[2]; }
      leadField[flat] = bestC;
    }
  }

  return { heightField, leadField };
}

// -----------------------------------------------------------------------------
// Separable Gaussian smoothing
// -----------------------------------------------------------------------------

function _gaussianKernel1D(sigma) {
  const radius = Math.max(1, Math.ceil(3 * sigma));
  const size = 2 * radius + 1;
  const k = new Float32Array(size);
  let sum = 0;
  for (let i = -radius; i <= radius; i++) {
    const v = Math.exp(-(i * i) / (2 * sigma * sigma));
    k[i + radius] = v;
    sum += v;
  }
  for (let i = 0; i < size; i++) k[i] /= sum;
  return { kernel: k, radius };
}

function _smoothField(field, gridW, gridH, sigma) {
  const { kernel, radius } = _gaussianKernel1D(sigma);
  const tmp = new Float32Array(gridW * gridH);
  const out = new Float32Array(gridW * gridH);

  // Horizontal pass.
  for (let y = 0; y < gridH; y++) {
    const rowOff = y * gridW;
    for (let x = 0; x < gridW; x++) {
      let acc = 0, wsum = 0;
      for (let i = -radius; i <= radius; i++) {
        const xi = x + i;
        if (xi < 0 || xi >= gridW) continue;
        const w = kernel[i + radius];
        acc += w * field[rowOff + xi];
        wsum += w;
      }
      tmp[rowOff + x] = wsum > 0 ? acc / wsum : 0;
    }
  }
  // Vertical pass.
  for (let y = 0; y < gridH; y++) {
    for (let x = 0; x < gridW; x++) {
      let acc = 0, wsum = 0;
      for (let i = -radius; i <= radius; i++) {
        const yi = y + i;
        if (yi < 0 || yi >= gridH) continue;
        const w = kernel[i + radius];
        acc += w * field[yi * gridW + x];
        wsum += w;
      }
      out[y * gridW + x] = wsum > 0 ? acc / wsum : 0;
    }
  }
  return out;
}

// -----------------------------------------------------------------------------
// Sampling leading channel inside a polygon ring
// -----------------------------------------------------------------------------

function _sampleLeadAtRing(ring, leadField, gridW, gridH) {
  // Sample centroid + 4 cardinal neighbours inside the ring's bbox midpoint.
  const { cx, cy, xmin, ymin, xmax, ymax } = _ringBoundsCentroid(ring);
  const dx = (xmax - xmin) * 0.15 + 1;
  const dy = (ymax - ymin) * 0.15 + 1;
  const samples = [
    [cx, cy],
    [cx + dx, cy],
    [cx - dx, cy],
    [cx, cy + dy],
    [cx, cy - dy],
  ];
  const counts = [0, 0, 0];
  for (const [sx, sy] of samples) {
    const ix = Math.max(0, Math.min(gridW - 1, Math.round(sx)));
    const iy = Math.max(0, Math.min(gridH - 1, Math.round(sy)));
    const v = leadField[iy * gridW + ix];
    if (v >= 0 && v <= 2) counts[v]++;
  }
  let best = 0, bestC = counts[0];
  if (counts[1] > bestC) { best = 1; bestC = counts[1]; }
  if (counts[2] > bestC) { best = 2; bestC = counts[2]; }
  return best;
}

// -----------------------------------------------------------------------------
// Main entry point
// -----------------------------------------------------------------------------

export function renderContours(svgEl, layout, weights, stride, opts) {
  if (!svgEl) throw new Error("contour_render.renderContours: svgEl is required");
  if (!layout || !layout.cells) {
    // Nothing to draw — clear any existing layer.
    _clearLayer(svgEl);
    return;
  }
  const o = opts || {};
  const width = +o.width || 800;
  const height = +o.height || 600;
  const marginPx = +o.marginPx || 40;

  const w = weights || { confidence: 1, patrilineal: 1, endogamy: 1 };
  let s = Math.round(+stride);
  if (!Number.isFinite(s) || s < 3) s = 7;
  if (s > 11) s = 11;

  const d3 = _ensureD3();

  // 1-2: per-cell channels (cached on layout).
  const cache = _computeChannels(layout);
  const channelCells = cache.cells;
  if (channelCells.length === 0) {
    _clearLayer(svgEl);
    return;
  }

  // 3-4: scaffolding for the chosen size; reuse if dimensions + cell count match.
  const key = _scaffoldKey(width, height, marginPx, channelCells.length);
  if (!_scaffold || _scaffold.key !== key || _scaffold.layout !== layout) {
    const sc = _buildScaffold(width, height, marginPx, channelCells);
    _scaffold = { key, layout, ...sc };
  }
  const scaffold = _scaffold;

  // 4: rasterize.
  const { heightField, leadField } = _rasterize(scaffold, channelCells, w, cache.hexRadius);

  // 5: smooth.
  const smoothed = _smoothField(heightField, scaffold.gridW, scaffold.gridH, 1.5);

  // 6: percentile levels.
  const sorted = Array.from(smoothed).filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  const percentiles = [];
  for (let i = 0; i < s; i++) {
    percentiles.push(50 + (i * (99 - 50)) / Math.max(1, s - 1));
  }
  let levels = percentiles.map((p) => _percentile(sorted, p));
  // Deduplicate flat regions to avoid d3-contour drawing zero-area rings.
  levels = _uniqueAscending(levels);
  if (levels.length === 0 || levels[levels.length - 1] <= 0) {
    _clearLayer(svgEl);
    return;
  }

  // 7: extract isolines.
  const contoursGen = d3.contours()
    .size([scaffold.gridW, scaffold.gridH])
    .thresholds(levels);
  const polygons = contoursGen(smoothed);

  // 8-9: render to a fresh group.
  const layer = _resetLayer(svgEl);

  for (const poly of polygons) {
    if (!poly || !poly.coordinates || poly.coordinates.length === 0) continue;
    // poly is a GeoJSON MultiPolygon: coordinates is array of polygons,
    // each polygon is array of rings, each ring is array of [x,y].
    for (const polygon of poly.coordinates) {
      if (!polygon || polygon.length === 0) continue;
      for (let r = 0; r < polygon.length; r++) {
        const ring = polygon[r];
        if (!ring || ring.length < 3) continue;
        const area = _signedArea(ring);
        const direction = area >= 0 ? "ccw" : "cw";
        const lead = _sampleLeadAtRing(ring, leadField, scaffold.gridW, scaffold.gridH);
        const channel = CHANNEL_NAMES[lead] || "confidence";
        const color = CHANNEL_COLORS[channel];
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("d", _ringToPath(ring, scaffold.gridToSvg));
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", color);
        path.setAttribute("stroke-width", "1");
        path.setAttribute("stroke-opacity", "0.6");
        if (direction === "cw") {
          path.setAttribute("stroke-dasharray", "3 2");
        }
        path.setAttribute("data-direction", direction);
        path.setAttribute("data-channel", channel);
        path.setAttribute("data-level", String(poly.value));
        layer.appendChild(path);
      }
    }
  }
}

function _uniqueAscending(arr) {
  const out = [];
  let prev = -Infinity;
  const sorted = arr.slice().sort((a, b) => a - b);
  for (const v of sorted) {
    if (v - prev > 1e-9) {
      out.push(v);
      prev = v;
    }
  }
  return out;
}

function _clearLayer(svgEl) {
  const existing = svgEl.querySelector(":scope > g.contour-layer");
  if (existing) existing.remove();
}

function _resetLayer(svgEl) {
  _clearLayer(svgEl);
  const g = document.createElementNS(SVG_NS, "g");
  g.setAttribute("class", "contour-layer");
  svgEl.appendChild(g);
  return g;
}
