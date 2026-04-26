<template>
  <div class="panel">
    <div class="panel-head">
      <span>V3 · Relation Embedding Space</span>
      <span class="legend-row">
        <!-- Both modes share the diverging score-gap palette (red → cream
             → green) and the same canonical packing, so one legend covers
             both. -->
        <span class="score-legend tiny">
          <span class="lbl">score gap</span>
          <span class="tick">−1</span>
          <span class="ramp gap-ramp"></span>
          <span class="tick">+1</span>
        </span>
        <span class="score-legend tiny" title="Background heatmap = training-cohort density">
          <span class="lbl">train ref</span>
          <span class="ramp ref-ramp"></span>
        </span>
      </span>
      <span class="tiny muted">{{ hint }}</span>
      <button class="mode-btn" @click="cycleMode" :title="`mode: ${mode}`">
        {{ modeLabel }}
      </button>
      <label class="topk-ctl tiny" v-if="mode === 'scatter'"
             title="Pairs per husband (1 = best-scoring; higher exposes hard negatives)">
        K
        <select v-model.number="topK" @change="redraw">
          <option :value="1">1</option>
          <option :value="3">3</option>
          <option :value="5">5</option>
          <option :value="8">8</option>
        </select>
      </label>
      <button v-if="mode === 'scatter'"
        class="mode-btn lasso-btn"
        :class="{ on: lassoOn }"
        @click="toggleLasso"
        title="Drag-rectangle select → V4"
      >{{ lassoOn ? '◩ lasso on' : '◩ lasso' }}</button>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v3')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body no-pad" ref="wrapRef">
      <svg ref="svgRef" class="hex-svg" @click="onCanvasClick" />
      <div v-if="loading" class="overlay">loading embeddings…</div>
      <div v-if="error" class="overlay err">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, onMounted, onUnmounted, watch } from 'vue'
import * as d3 from 'd3'
import { hexPath } from '../utils/hex.js'
import { getEmbedding } from '../api/client.js'
import bus from '../utils/eventbus.js'

// Canonical (verbatim) hex algorithm from D:/projects/VIS_2026/NEW/viz/js/.
// These two modules implement the iterative inward-attraction packing,
// the diverging score-gap fill (#993c1d → #f5f1e8 → #0f6e56), the cluster
// borders, and the outlier stripe overlay. Used only for `mode === 'honeycomb'`.
import { buildHoneycomb } from '../canonical/cluster_layout.js'
import { renderHoneycomb } from '../canonical/honeycomb_render.js'

const svgRef = ref(null)
const wrapRef = ref(null)
const loading = ref(true)
const error = ref(null)

const appState = inject('appState')

// 2 modes:
//   'honeycomb' — verbatim viz/ algorithm. Cluster-packed cells, score-gap
//                 diverging fill, cluster borders, outlier stripes. Click
//                 a hex → V4/V5.
//   'scatter'   — raw MDS dots over X-means + density-contour background;
//                 supports lasso for multi-point selection.
const MODES = ['honeycomb', 'scatter']
const mode = ref('honeycomb')
const modeLabel = computed(() =>
  mode.value === 'honeycomb' ? '⬢ honeycomb' : '• scatter'
)
const hint = computed(() =>
  mode.value === 'honeycomb'
    ? 'click a hex; cluster borders mark cluster boundaries'
    : 'X-means + density contour · click a point · drag-lasso for multi-select'
)
function cycleMode() {
  mode.value = MODES[(MODES.indexOf(mode.value) + 1) % MODES.length]
  draw()
}

const lassoOn = ref(false)
function toggleLasso() {
  lassoOn.value = !lassoOn.value
  if (lassoOn.value) mode.value = 'scatter'
  draw()
}

const topK = ref(3)

// (stroke palette inlined where used; clusterPalette removed with X-means)

let data = null
let selected = ref(null)
const acceptedSet = ref(new Set())

function resizeHandler() { draw() }

async function load() {
  loading.value = true
  error.value = null
  try {
    data = await getEmbedding({ year: appState.year, ablation: appState.ablation })
    loading.value = false
    draw()
  } catch (e) {
    loading.value = false
    error.value = `cohort_${appState.year}.json unavailable: ${e.message || e}`
    console.warn(e)
  }
}

function redraw() { draw() }

// ──────────────────────────────────────────────────────────────────────
// Mode dispatch
// ──────────────────────────────────────────────────────────────────────
//
// Both modes share the same coordinate system. The canonical packing
// algorithm (`buildHoneycomb`) normalizes `mds_coords` to [0,1]² internally
// using the cohort's own min/max, so for the heatmap to align we must
// pre-normalize `train_ref_coords` with the same min/max.
function buildSharedLayout() {
  // Run the canonical packing once. Both modes consume `cells` for cell-
  // assignment lookup.
  const layout = buildHoneycomb({
    pairs: data.pairs,
    mds_coords: data.mds_coords,
    clusters: data.clusters,
    k_clusters: data.k_clusters,
  })
  // Compute the same min/max the canonical algorithm used so we can
  // normalize the training-reference coords into the same [0,1]² space.
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
  for (const c of data.mds_coords) {
    if (c[0] < xMin) xMin = c[0]; if (c[0] > xMax) xMax = c[0]
    if (c[1] < yMin) yMin = c[1]; if (c[1] > yMax) yMax = c[1]
  }
  const xRange = (xMax - xMin) || 1
  const yRange = (yMax - yMin) || 1
  const refRaw = data.train_ref_coords || []
  const refNorm = refRaw.map(([x, y]) => [
    (x - xMin) / xRange,
    (y - yMin) / yRange,
  ])
  return { layout, refNorm }
}

function draw() {
  if (!svgRef.value || !wrapRef.value || !data) return
  const wrap = wrapRef.value.getBoundingClientRect()
  const W = wrap.width, H = wrap.height
  if (W === 0 || H === 0) return
  const svg = svgRef.value
  while (svg.firstChild) svg.removeChild(svg.firstChild)
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`)

  const { layout, refNorm } = buildSharedLayout()

  // 1) Foreground (mode-specific). Honeycomb mode internally clears the
  //    SVG, so we have to render it BEFORE the heatmap, then prepend the
  //    heatmap layer to put it visually behind everything else.
  if (mode.value === 'honeycomb') drawHoneycomb(svg, layout, W, H)
  else drawScatter(svg, layout, W, H)

  // 2) Heatmap layer — appended then re-positioned to the bottom of the
  //    SVG child list so it sits behind cells / dots / cluster borders.
  drawTrainRefHeatmap(svg, refNorm, W, H)
  const heatmap = svg.querySelector('.train-ref-heatmap')
  if (heatmap && svg.firstChild && svg.firstChild !== heatmap) {
    svg.insertBefore(heatmap, svg.firstChild)
  }
}

// ──────────────────────────────────────────────────────────────────────
// Honeycomb mode — wraps the canonical algorithm
// ──────────────────────────────────────────────────────────────────────
// Shared coordinate transform — must match the canonical renderer
// (honeycomb_render.js) so all three layers (heatmap, scatter dots, hex
// cells) live in the same pixel space. The renderer uses
//   scale = min(innerW, innerH); offsetX = marginPx + (innerW - scale)/2;
//   offsetY = marginPx + (innerH - scale)/2;
// ...so layout coords in [0,1]² → a square inscribed in the SVG.
const MARGIN_PX = 40
function pxTransform(W, H) {
  const innerW = W - 2 * MARGIN_PX
  const innerH = H - 2 * MARGIN_PX
  const scale = Math.min(innerW, innerH)
  const offsetX = MARGIN_PX + (innerW - scale) / 2
  const offsetY = MARGIN_PX + (innerH - scale) / 2
  return {
    x: (cx) => offsetX + cx * scale,
    y: (cy) => offsetY + cy * scale,
    scale,
    offsetX,
    offsetY,
  }
}

// Heatmap of training-reference relations — drawn first so cells/dots
// overlay on top. Empty when train_ref_coords is missing or empty.
function drawTrainRefHeatmap(svg, refNorm, W, H) {
  if (!refNorm || refNorm.length < 5) return
  const t = pxTransform(W, H)
  const screen = refNorm.map(([cx, cy]) => [t.x(cx), t.y(cy)])
  const innerW = W - 2 * MARGIN_PX
  const innerH = H - 2 * MARGIN_PX
  const contours = d3.contourDensity()
    .x(p => p[0]).y(p => p[1])
    .size([W, H])
    .bandwidth(20)
    .thresholds(8)(screen)
  const cMax = d3.max(contours, c => c.value) || 1
  // Cool sand → warm amber so the layer reads as background but still
  // signals where the training-cohort density is concentrated.
  const cScale = d3.scaleSequential(
    d3.interpolateRgb('#f1ecdf', '#d4a85d')
  ).domain([0, cMax])
  const g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
  g.setAttribute('class', 'train-ref-heatmap')
  const path = d3.geoPath()
  for (const c of contours) {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    p.setAttribute('d', path(c) || '')
    p.setAttribute('fill', cScale(c.value))
    p.setAttribute('fill-opacity', '0.45')
    p.setAttribute('stroke', '#b89656')
    p.setAttribute('stroke-width', '0.3')
    p.setAttribute('stroke-opacity', '0.55')
    g.appendChild(p)
  }
  svg.appendChild(g)
}

// Honeycomb mode — defers entirely to the canonical renderer.
function drawHoneycomb(svg, layout, W, H) {
  const opts = { width: W, height: H, marginPx: MARGIN_PX }
  renderHoneycomb(svg, layout, opts)
  // Listeners attached once in onMounted; canonical SVG dispatches
  // cell-clicked / cell-hovered with the full cell record.
}

function onCanonicalCellClick(ev) {
  // Only respond when honeycomb mode is active and we have data.
  if (mode.value !== 'honeycomb' || !data) return
  const cell = ev.detail || {}
  const pairIds = cell.pairIds || []
  const pairs = pairIds.map(i => pairPayload(data.pairs[i], i)).filter(Boolean)
  if (!pairs.length) {
    // Empty cell click — clear selection downstream
    bus.emit('hex-clear')
    selected.value = null
    return
  }
  bus.emit('hex-select', { binKey: `cell:${cell.id}`, pairs })
  selected.value = { kind: 'cell', id: cell.id }
}
function onCanonicalCellHover(_ev) {
  // Hover not yet wired into linked highlights.
}

// ──────────────────────────────────────────────────────────────────────
// Scatter mode — same canonical packing as honeycomb (one position per
// pair, derived from `layout.cells[k].pairIds`), just rendered as dots
// instead of an aggregated hex glyph. Multi-pair cells get an
// in-hex-radius jitter so dots don't perfectly stack.
// ──────────────────────────────────────────────────────────────────────
function _hashJitter(seed, idx, scale = 0.6) {
  // Tiny deterministic in-cell jitter so reloads don't reshuffle dots.
  // Two coprime LCG-style steps on (seed, idx).
  const a = ((seed * 1103515245 + idx * 12345) >>> 0) / 0xffffffff
  const b = ((seed * 1664525 + idx * 1013904223) >>> 0) / 0xffffffff
  const ang = a * Math.PI * 2
  const r = Math.sqrt(b) * scale       // sqrt for area-uniform jitter
  return [Math.cos(ang) * r, Math.sin(ang) * r]
}

function shapeCellScatter(layout) {
  // For each populated cell, emit one point per pair at the cell's
  // canonical centroid + small in-hex jitter. Top-K filter applies per
  // husband AFTER cell assignment so we keep the alignment honest.
  const out = []
  const cells = layout?.cells || []
  for (const cell of cells) {
    const ids = cell.pairIds || []
    if (!ids.length) continue
    let i = 0
    for (const pid of ids) {
      const p = data.pairs[pid]
      if (!p) { i++; continue }
      if (acceptedSet.value.has(`${p.husband_id}|${p.wife_id}`)) { i++; continue }
      // Jitter scale = 0.6 of the hex radius (cluster_layout default 0.04).
      const [jx, jy] = ids.length > 1
        ? _hashJitter(cell.id, i, (layout.meta?.hexRadius ?? 0.04) * 0.6)
        : [0, 0]
      out.push({
        id: pid,
        cellId: cell.id,
        x: cell.cx + jx,
        y: cell.cy + jy,
        score_gap: p.score_gap,
        raw_score: p.score,
        score: 1 / (1 + Math.exp(-p.score)),
        label: p.label,
        pair_type: p.label === 1 ? 'gt' : 'pred',
        hungarian_correct: p.hungarian_correct,
        male_idx: p.husband_id,
        female_idx: p.wife_id,
        same_lineage: p.same_lineage,
        era: p.era,
        patri_path_count: p.patri_path_count,
        cluster: cell.cluster,
      })
      i++
    }
  }
  // Top-K per husband, by raw score.
  if (topK.value >= out.length) return out
  const byMale = new Map()
  for (const p of out) {
    if (!byMale.has(p.male_idx)) byMale.set(p.male_idx, [])
    byMale.get(p.male_idx).push(p)
  }
  const trimmed = []
  for (const arr of byMale.values()) {
    arr.sort((a, b) => b.raw_score - a.raw_score)
    trimmed.push(...arr.slice(0, topK.value))
  }
  return trimmed
}

// Diverging score-gap palette — same anchors as honeycomb_render.js.
function gapColor(g) {
  // Clamp to [-1, +1] for the linear interpolation.
  const v = Math.max(-1, Math.min(1, g ?? 0))
  if (v <= 0) {
    // -1..0  →  #993c1d → #f5f1e8
    return d3.interpolateRgb('#993c1d', '#f5f1e8')(v + 1)
  }
  // 0..+1  →  #f5f1e8 → #0f6e56
  return d3.interpolateRgb('#f5f1e8', '#0f6e56')(v)
}

function drawScatter(svg, layout, W, H) {
  const t = pxTransform(W, H)
  const points = shapeCellScatter(layout)
  // Use a top-level <g> in the same coordinate system as the canonical
  // renderer so the lasso, dots, and (later-prepended) heatmap all line up.
  const root = d3.select(svg).append('g').attr('class', 'scatter')
  root.selectAll('circle').data(points).enter().append('circle')
    .attr('cx', p => t.x(p.x)).attr('cy', p => t.y(p.y))
    .attr('r', p => p.pair_type === 'pred' ? 2.4 : 3.2)
    .attr('fill', p => gapColor(p.score_gap))
    .attr('stroke', '#6d6458')
    .attr('stroke-width', p => p.pair_type === 'pred' ? 0.3 : 0.5)
    .attr('stroke-dasharray', p => p.pair_type === 'pred' ? '1.5 1.5' : null)
    .attr('fill-opacity', p => p.pair_type === 'pred' ? 0.78 : 1.0)
    .style('cursor', 'pointer')
    .on('click', (event, p) => {
      event.stopPropagation()
      root.selectAll('circle').attr('stroke', '#6d6458')
        .attr('stroke-width', d => d.pair_type === 'pred' ? 0.3 : 0.5)
      d3.select(event.currentTarget).attr('stroke', '#d46a3b').attr('stroke-width', 2.0)
      bus.emit('hex-select', {
        binKey: `pt:${p.male_idx}-${p.female_idx}`,
        pairs: [pairPayload(data.pairs[p.id], p.id)],
      })
    })

  if (lassoOn.value) attachLasso(root, t, W, H, points)
}

function attachLasso(root, t, W, H, points) {
  // Brush operates in pixel coordinates over the full SVG; we filter
  // points by their pixel position via the same `t` transform.
  const brush = d3.brush()
    .extent([[0, 0], [W, H]])
    .on('end', (event) => {
      if (!event.selection) return
      const [[x0, y0], [x1, y1]] = event.selection
      const picked = points.filter(p => {
        const sx = t.x(p.x), sy = t.y(p.y)
        return sx >= x0 && sx <= x1 && sy >= y0 && sy <= y1
      })
      if (!picked.length) return
      bus.emit('hex-select', {
        binKey: `lasso:${picked.length}`,
        pairs: picked.map(p => pairPayload(data.pairs[p.id], p.id)),
      })
    })
  const lg = root.append('g').attr('class', 'lasso')
  lg.call(brush)
  lg.selectAll('.overlay').attr('fill-opacity', 0)
}

// ──────────────────────────────────────────────────────────────────────
// Shared helpers
// ──────────────────────────────────────────────────────────────────────
//
// Note: the on-the-fly X-means / convex hulls used in the previous scatter
// implementation are gone. Both modes now use the canonical packing's
// cluster assignment (cohort.clusters), which is what `cluster_layout.js`
// reads to colour cells and route cluster borders. Keeping a second
// clustering on top would be redundant and would drift away from the
// honeycomb mode's borders, breaking the visual alignment.
function pairPayload(p, idx) {
  if (!p) return null
  return {
    id: p.id ?? idx,
    husband_id: p.husband_id,
    wife_id: p.wife_id,
    score: p.score,
    score_gap: p.score_gap,
    label: p.label,
    hungarian_correct: p.hungarian_correct,
    same_lineage: p.same_lineage,
    era: p.era,
    pair_type: p.label === 1 ? 'gt' : 'pred',
    cluster: data?.clusters?.[idx],
    patri_path_count: p.patri_path_count,
  }
}

function onCanvasClick(event) {
  // Background-click → clear selection. Cell clicks bubble up to here
  // too (the canonical renderer doesn't stopPropagation), so we have to
  // distinguish between the SVG itself and a child element. Treat any
  // click whose target is a child polygon/path/g as a "real" cell hit
  // and leave the selection alone.
  const t = event && event.target
  if (t && t !== svgRef.value) return
  if (selected.value) {
    selected.value = null
    bus.emit('hex-clear')
  }
}

watch(() => `${appState.year}|${appState.ablation}`, () => { load() })

function onAccepted(evt) {
  if (!evt || evt.husband_id == null || evt.wife_id == null) return
  acceptedSet.value.add(`${evt.husband_id}|${evt.wife_id}`)
  draw()
}

onMounted(() => {
  load()
  window.addEventListener('resize', resizeHandler)
  bus.on('match-accepted', onAccepted)
  // Attach the canonical cell-click / cell-hover listeners on the SVG
  // ONCE. drawHoneycomb wipes child elements but never replaces svgRef
  // itself, so a single bind here survives every redraw.
  if (svgRef.value) {
    svgRef.value.addEventListener('cell-clicked', onCanonicalCellClick)
    svgRef.value.addEventListener('cell-hovered', onCanonicalCellHover)
  }
})
onUnmounted(() => {
  window.removeEventListener('resize', resizeHandler)
  bus.off('match-accepted', onAccepted)
  if (svgRef.value) {
    svgRef.value.removeEventListener('cell-clicked', onCanonicalCellClick)
    svgRef.value.removeEventListener('cell-hovered', onCanonicalCellHover)
  }
})
</script>

<style lang="less" scoped>
.hex-svg { width: 100%; height: 100%; display: block; }
.mode-btn {
  font-size: 10px; padding: 1px 6px; margin-left: 4px;
  border: 1px solid #888; border-radius: 3px;
  background: #f5f5f5; cursor: pointer; color: #1a1a1a;
  &:hover { background: #ffe082; border-color: #d4a85d; }
  &.on { background: #ffe082; border-color: #d4a85d; font-weight: 700; }
}
.topk-ctl {
  display: inline-flex; align-items: center; gap: 2px;
  margin-left: 4px; color: #555;
  select {
    font-size: 10px; padding: 0 2px; border: 1px solid #888; border-radius: 3px;
    background: #f5f5f5; color: #1a1a1a;
  }
}
.legend-row {
  display: flex; gap: 8px; align-items: center;
  .score-legend {
    display: inline-flex; align-items: center; gap: 4px;
    color: #555; font-size: 10px;
    .lbl { color: #333; }
    .ramp {
      display: inline-block; width: 72px; height: 8px; border-radius: 2px;
      border: 1px solid #c8bfa8;
    }
    .ramp.gap-ramp {
      background: linear-gradient(to right, #993c1d 0%, #f5f1e8 50%, #0f6e56 100%);
    }
    .ramp.ref-ramp {
      width: 36px;
      background: linear-gradient(to right, #f1ecdf 0%, #d4a85d 100%);
    }
    .tick { font-size: 9px; color: #888; font-variant-numeric: tabular-nums; }
  }
}
.overlay {
  position: absolute; inset: 0;
  display: grid; place-items: center;
  color: #555; font-size: 12px;
  background: rgba(255,255,255,0.6);
  &.err { color: #a40000; }
}
.panel-body { position: relative; }
</style>
