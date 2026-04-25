<template>
  <div class="panel">
    <div class="panel-head">
      <span>V3 · Relation Embedding Space</span>
      <span class="legend-row">
        <!-- Honeycomb-mode legend uses the diverging score-gap palette
             from viz/js/honeycomb_render.js (red → cream → green) so the
             rendered hexes match the canonical viewer exactly. -->
        <template v-if="mode === 'honeycomb'">
          <span class="score-legend tiny">
            <span class="lbl">score gap</span>
            <span class="tick">−1</span>
            <span class="ramp gap-ramp"></span>
            <span class="tick">+1</span>
          </span>
        </template>
        <template v-else>
          <span class="score-legend tiny">
            <span class="lbl">HGT score</span>
            <span class="tick">0</span>
            <span class="ramp hgt-ramp"></span>
            <span class="tick">1</span>
          </span>
        </template>
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

const STROKE_REST = '#6d6458'
const STROKE_SELECT = '#d46a3b'
const clusterPalette = d3.schemeSet2

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
function draw() {
  if (!svgRef.value || !wrapRef.value || !data) return
  const wrap = wrapRef.value.getBoundingClientRect()
  const W = wrap.width, H = wrap.height
  if (W === 0 || H === 0) return
  const svg = svgRef.value
  // Clear and reset basic attrs; the canonical renderer will rewrite for
  // honeycomb mode, the d3 path below for scatter mode.
  while (svg.firstChild) svg.removeChild(svg.firstChild)
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`)
  if (mode.value === 'honeycomb') drawHoneycomb(W, H)
  else drawScatter(W, H)
}

// ──────────────────────────────────────────────────────────────────────
// Honeycomb mode — wraps the canonical algorithm
// ──────────────────────────────────────────────────────────────────────
function drawHoneycomb(W, H) {
  const svg = svgRef.value
  // The canonical renderer wants the full cohort JSON shape.
  // Build a layout once per (year, ablation) — algorithm has no top-K.
  const cohortLike = {
    pairs: data.pairs,
    mds_coords: data.mds_coords,
    clusters: data.clusters,
    k_clusters: data.k_clusters,
  }
  const layout = buildHoneycomb(cohortLike)
  const opts = { width: W, height: H, marginPx: 40 }
  renderHoneycomb(svg, layout, opts)
  // Listeners are attached once in onMounted (see below) — re-binding here
  // would leak handlers on every draw and fire bus events 2×, 3×, … per
  // click as the user pans through cohorts.
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
// Scatter mode — preserves the ASight pipeline + lasso
// ──────────────────────────────────────────────────────────────────────
function shapeActivePoints() {
  if (!data || !data.pairs?.length) return []
  const xs = data.mds_coords.map(c => c[0])
  const ys = data.mds_coords.map(c => c[1])
  const xMin = d3.min(xs), xMax = d3.max(xs)
  const yMin = d3.min(ys), yMax = d3.max(ys)
  const xSpan = (xMax - xMin) || 1
  const ySpan = (yMax - yMin) || 1
  const pts = data.pairs.map((p, i) => {
    const [mx, my] = data.mds_coords[i] || [0, 0]
    return {
      id: p.id,
      x: (mx - xMin) / xSpan,
      y: (my - yMin) / ySpan,
      score: 1 / (1 + Math.exp(-p.score)),
      raw_score: p.score,
      score_gap: p.score_gap,
      pair_type: p.label === 1 ? 'gt' : 'pred',
      label: p.label,
      hungarian_correct: p.hungarian_correct,
      male_idx: p.husband_id,
      female_idx: p.wife_id,
      same_lineage: p.same_lineage,
      era: p.era,
      patri_path_count: p.patri_path_count,
      cluster: data.clusters?.[i],
    }
  })
  const filtered = pts.filter(p => !acceptedSet.value.has(`${p.male_idx}|${p.female_idx}`))
  if (topK.value >= filtered.length) return filtered
  const byMale = new Map()
  for (const p of filtered) {
    if (!byMale.has(p.male_idx)) byMale.set(p.male_idx, [])
    byMale.get(p.male_idx).push(p)
  }
  const out = []
  for (const arr of byMale.values()) {
    arr.sort((a, b) => b.raw_score - a.raw_score)
    out.push(...arr.slice(0, topK.value))
  }
  return out
}

function drawScatter(W, H) {
  const pad = 14
  const innerW = W - pad * 2
  const innerH = H - pad * 2
  const x = d3.scaleLinear().domain([0, 1]).range([0, innerW])
  const y = d3.scaleLinear().domain([0, 1]).range([innerH, 0])
  const svg = d3.select(svgRef.value)
  const root = svg.append('g').attr('transform', `translate(${pad},${pad})`)
  const activePoints = shapeActivePoints()

  const fillScale = d3.scaleSequential(
    d3.interpolateRgbBasis(['#fff7d6','#f5c04e','#e07b3a','#9d2466','#2a1a6b'])
  ).domain([0, 1])

  // Density contour
  const screenPts = activePoints.map(p => [x(p.x), y(p.y)])
  if (screenPts.length > 0) {
    const contours = d3.contourDensity()
      .x(d => d[0]).y(d => d[1])
      .size([innerW, innerH])
      .bandwidth(22).thresholds(10)(screenPts)
    const cScale = d3.scaleSequential(d3.interpolate('#f3ecdf', '#3a3d42'))
      .domain([0, d3.max(contours, c => c.value) || 1])
    root.append('g').attr('class', 'contour')
      .selectAll('path').data(contours).enter().append('path')
      .attr('d', d3.geoPath())
      .attr('fill', d => cScale(d.value)).attr('fill-opacity', 0.55)
      .attr('stroke', '#8b8378').attr('stroke-width', 0.35)
  }

  // X-means hulls
  if (screenPts.length >= 4) {
    const best = pickKByBic(screenPts, 2,
      Math.min(8, Math.max(2, Math.floor(screenPts.length / 30))))
    if (best) {
      const hulls = clusterHulls(screenPts, best.labels, best.k)
      const hullG = root.append('g').attr('class', 'hulls')
      hullG.selectAll('path').data(hulls).enter().append('path')
        .attr('d', d => `M${d.hull.map(p => p.join(',')).join('L')}Z`)
        .attr('fill', d => clusterPalette[d.c % clusterPalette.length])
        .attr('fill-opacity', 0.18)
        .attr('stroke', d => clusterPalette[d.c % clusterPalette.length])
        .attr('stroke-width', 1.4)
        .attr('stroke-dasharray', '3 2')
      hullG.selectAll('text').data(hulls).enter().append('text')
        .attr('x', d => d3.polygonCentroid(d.hull)[0])
        .attr('y', d => d3.polygonCentroid(d.hull)[1])
        .attr('text-anchor', 'middle')
        .attr('font-size', 11).attr('font-weight', 700)
        .attr('fill', d => d3.color(clusterPalette[d.c % clusterPalette.length]).darker(1.2))
        .text(d => `k${d.c + 1}`)
    }
  }

  // Scatter dots
  const g = root.append('g').attr('class', 'scatter')
  g.selectAll('circle').data(activePoints).enter().append('circle')
    .attr('cx', p => x(p.x)).attr('cy', p => y(p.y))
    .attr('r', p => p.pair_type === 'pred' ? 2.6 : 3.4)
    .attr('fill', p => fillScale(p.score))
    .attr('stroke', STROKE_REST)
    .attr('stroke-width', p => p.pair_type === 'pred' ? 0.3 : 0.5)
    .attr('stroke-dasharray', p => p.pair_type === 'pred' ? '1.5 1.5' : null)
    .attr('fill-opacity', p => p.pair_type === 'pred' ? 0.75 : 1.0)
    .style('cursor', 'pointer')
    .on('click', (event, p) => {
      event.stopPropagation()
      g.selectAll('circle')
        .attr('stroke', STROKE_REST)
        .attr('stroke-width', d => d.pair_type === 'pred' ? 0.3 : 0.5)
      d3.select(event.currentTarget).attr('stroke', STROKE_SELECT).attr('stroke-width', 2.0)
      bus.emit('hex-select', {
        binKey: `pt:${p.male_idx}-${p.female_idx}`,
        pairs: [pairPayload(data.pairs[p.id], p.id)],
      })
    })

  if (lassoOn.value) attachLasso(root, innerW, innerH, activePoints, x, y)
}

function attachLasso(root, innerW, innerH, activePoints, x, y) {
  const brush = d3.brush()
    .extent([[0, 0], [innerW, innerH]])
    .on('end', (event) => {
      if (!event.selection) return
      const [[x0, y0], [x1, y1]] = event.selection
      const picked = activePoints.filter(p => {
        const sx = x(p.x), sy = y(p.y)
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
// X-means utilities (used in scatter mode only — honeycomb mode uses
// the cluster ids that `cluster_layout.js` reads from cohort.clusters).
// ──────────────────────────────────────────────────────────────────────
function kmeansPP(pts, k, rng = Math.random) {
  const n = pts.length
  if (n === 0) return { centers: [], labels: [] }
  const centers = [pts[Math.floor(rng() * n)].slice()]
  while (centers.length < k) {
    const d2 = pts.map(p => {
      let best = Infinity
      for (const c of centers) {
        const dx = p[0] - c[0], dy = p[1] - c[1]
        const d = dx*dx + dy*dy
        if (d < best) best = d
      }
      return best
    })
    const sum = d2.reduce((a, b) => a + b, 0)
    let r = rng() * sum, idx = 0
    for (; idx < n; idx++) { r -= d2[idx]; if (r <= 0) break }
    centers.push(pts[Math.min(idx, n - 1)].slice())
  }
  return runKmeans(pts, centers)
}
function runKmeans(pts, centers, maxIter = 40) {
  const n = pts.length, k = centers.length
  const labels = new Array(n).fill(0)
  for (let it = 0; it < maxIter; it++) {
    let changed = false
    for (let i = 0; i < n; i++) {
      let best = 0, bd = Infinity
      for (let j = 0; j < k; j++) {
        const dx = pts[i][0] - centers[j][0], dy = pts[i][1] - centers[j][1]
        const d = dx*dx + dy*dy
        if (d < bd) { bd = d; best = j }
      }
      if (labels[i] !== best) { labels[i] = best; changed = true }
    }
    const sums = Array.from({ length: k }, () => [0, 0, 0])
    for (let i = 0; i < n; i++) {
      const L = labels[i]
      sums[L][0] += pts[i][0]; sums[L][1] += pts[i][1]; sums[L][2] += 1
    }
    for (let j = 0; j < k; j++) {
      if (sums[j][2] > 0) {
        centers[j][0] = sums[j][0] / sums[j][2]
        centers[j][1] = sums[j][1] / sums[j][2]
      }
    }
    if (!changed) break
  }
  return { centers, labels }
}
function wss(pts, labels, centers) {
  let s = 0
  for (let i = 0; i < pts.length; i++) {
    const c = centers[labels[i]]
    const dx = pts[i][0] - c[0], dy = pts[i][1] - c[1]
    s += dx*dx + dy*dy
  }
  return s
}
function pickKByBic(pts, kMin = 2, kMax = 8) {
  let best = null
  const n = pts.length
  for (let k = kMin; k <= kMax; k++) {
    if (k >= n) break
    const { centers, labels } = kmeansPP(pts, k)
    const w = wss(pts, labels, centers)
    const sigma2 = w / Math.max(1, n - k)
    const L = -n / 2 * Math.log(2 * Math.PI * sigma2 + 1e-12) - w / (2 * sigma2 + 1e-12)
    const p = k * 2 + k
    const bic = -2 * L + p * Math.log(n)
    if (!best || bic < best.bic) best = { bic, k, centers, labels }
  }
  return best
}
function clusterHulls(pts, labels, k) {
  const hulls = []
  for (let c = 0; c < k; c++) {
    const grp = pts.filter((_, i) => labels[i] === c)
    if (grp.length < 3) continue
    const hull = d3.polygonHull(grp)
    if (hull) hulls.push({ c, hull })
  }
  return hulls
}

// ──────────────────────────────────────────────────────────────────────
// Shared helpers
// ──────────────────────────────────────────────────────────────────────
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
    .ramp.hgt-ramp {
      background: linear-gradient(to right,
        #fff7d6 0%, #f5c04e 25%, #e07b3a 50%, #9d2466 75%, #2a1a6b 100%);
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
