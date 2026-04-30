<template>
  <div class="panel">
    <div class="panel-head">
      <span>V3: Embedding View</span>
      <span class="legend-row">
        <span v-if="colorMode === 'gap'" class="score-legend tiny" title="ψ(m,w_true) − ψ(m,w_best_neg) for positives; ψ(m,w_neg) − ψ(m,w_true) for hard-negs. Anchors saturate at ±2 logits.">
          <span class="lbl">score gap</span>
          <span class="tick">−2</span>
          <span class="ramp gap-ramp"></span>
          <span class="tick">+2</span>
        </span>
        <span v-else class="score-legend tiny" title="HGT raw logit, GT-free. Anchors at the cohort min/max — sequential ramp, NOT a correctness signal.">
          <span class="lbl">HGT score</span>
          <span class="tick">low</span>
          <span class="ramp seq-ramp"></span>
          <span class="tick">high</span>
        </span>
        <span class="score-legend tiny" title="Background heatmap = training-cohort density">
          <span class="lbl">train ref</span>
          <span class="ramp ref-ramp"></span>
        </span>
      </span>
      <span class="tiny muted">{{ hint }}</span>
      <button class="mode-btn color-mode-btn" @click="cycleColorMode"
              :title="colorMode === 'gap'
                ? 'eval mode (GT-aware): cell color = mean score_gap (red=wrong, green=right)'
                : 'deploy mode (GT-free): cell color = mean HGT score (sequential, confidence only — NOT correctness)'">
        {{ colorMode === 'gap' ? '⚖ eval' : '↪ deploy' }}
      </button>
      <button class="mode-btn" @click="cycleMode" :title="`mode: ${mode}`">
        {{ modeLabel }}
      </button>
      <label class="topk-ctl tiny" v-if="mode !== 'honeycomb'"
             title="Pairs per husband for the dot layer (1 = best-scoring; higher exposes hard negatives)">
        K
        <select v-model.number="topK" @change="redraw">
          <option :value="1">1</option>
          <option :value="3">3</option>
          <option :value="5">5</option>
          <option :value="8">8</option>
        </select>
      </label>
      <button v-if="mode !== 'honeycomb'"
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
import { getEmbedding } from '../api/client.js'
import bus from '../utils/eventbus.js'

import { buildHoneycomb } from '../canonical/cluster_layout.js'
import { renderHoneycomb } from '../canonical/honeycomb_render.js'

const svgRef = ref(null)
const wrapRef = ref(null)
const loading = ref(true)
const error = ref(null)

const appState = inject('appState')

// 3 modes:
//   'honeycomb' — canonical packed cells, score-gap diverging fill,
//                 cluster borders, outlier stripes. Click hex → V4/V5.
//   'scatter'   — one dot per pair at its RAW (normalised) mds_coords.
//                 The model's actual learned 2-D embedding.
//   'mixed'     — translucent hexes + dots positioned at packer cells.
//                 Both layers visually coincide so the aggregate matches
//                 the per-pair detail.
const MODES = ['honeycomb', 'scatter', 'mixed']
const mode = ref('honeycomb')
const modeLabel = computed(() =>
  mode.value === 'honeycomb' ? '⬢ honeycomb'
  : mode.value === 'scatter' ? '• scatter'
  : '⬢• mixed'
)
const hint = computed(() =>
  mode.value === 'honeycomb'
    ? 'click a hex; cluster borders mark cluster boundaries'
    : mode.value === 'scatter'
    ? 'raw MDS embedding · click a dot · drag-lasso for multi-select'
    : 'mixed: translucent hex aggregate + raw dots on top'
)
function cycleMode() {
  mode.value = MODES[(MODES.indexOf(mode.value) + 1) % MODES.length]
  draw()
}

// Color mode toggles between GT-dependent gap diverging palette ('gap', eval)
// and GT-free score sequential palette ('score', deploy).
const COLOR_MODE_KEY = 'cmgpd-v3-color-mode'
const colorMode = ref(localStorage.getItem(COLOR_MODE_KEY) === 'score' ? 'score' : 'gap')
function cycleColorMode() {
  colorMode.value = colorMode.value === 'gap' ? 'score' : 'gap'
  try { localStorage.setItem(COLOR_MODE_KEY, colorMode.value) } catch {}
  draw()
}

const lassoOn = ref(false)
function toggleLasso() {
  lassoOn.value = !lassoOn.value
  if (lassoOn.value && mode.value === 'honeycomb') mode.value = 'scatter'
  draw()
}

const topK = ref(3)

let data = null
let selected = ref(null)
const acceptedSet = ref(new Set())

function resizeHandler() { draw() }
function onPanelResized({ ids } = {}) {
  if (Array.isArray(ids) && !ids.includes('v3')) return
  draw()
}

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
// Coordinate-system helpers
// ──────────────────────────────────────────────────────────────────────
// MDS routinely produces a few extreme outliers (1–5% of points) that
// stretch min/max by 3–5×, compressing 90% of pairs into ~6% of the
// visual area. Using 2nd–98th percentile bounds keeps 96% of pairs
// fully visible and pins the 4% extreme outliers at the canvas edge.
function getNormBoundsPercentile(pLo = 2, pHi = 98) {
  const mds = data.mds_coords || []
  if (!mds.length) return { xMin: 0, xMax: 1, yMin: 0, yMax: 1, xRange: 1, yRange: 1 }
  const xs = mds.map(c => c[0]).slice().sort((a, b) => a - b)
  const ys = mds.map(c => c[1]).slice().sort((a, b) => a - b)
  const pct = (arr, p) => arr[Math.max(0, Math.min(arr.length - 1, Math.round((arr.length - 1) * p / 100)))]
  const xMin = pct(xs, pLo), xMax = pct(xs, pHi)
  const yMin = pct(ys, pLo), yMax = pct(ys, pHi)
  return { xMin, xMax, yMin, yMax, xRange: (xMax - xMin) || 1, yRange: (yMax - yMin) || 1 }
}

function normalizeRef(refRaw, b) {
  return (refRaw || []).map(([x, y]) => [
    Math.max(0, Math.min(1, (x - b.xMin) / b.xRange)),
    Math.max(0, Math.min(1, (y - b.yMin) / b.yRange)),
  ])
}

function draw() {
  if (!svgRef.value || !wrapRef.value || !data) return
  const wrap = wrapRef.value.getBoundingClientRect()
  const W = wrap.width, H = wrap.height
  if (W === 0 || H === 0) return
  const svg = svgRef.value
  while (svg.firstChild) svg.removeChild(svg.firstChild)
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`)

  // Percentile bounds — cluster_layout.js also uses percentile bounds
  // internally so heatmap, scatter dots, and hex cells share one frame.
  const bounds = getNormBoundsPercentile(2, 98)
  const refNorm = normalizeRef(data.train_ref_coords, bounds)
  const showHex = (mode.value === 'honeycomb' || mode.value === 'mixed')
  const showDots = (mode.value === 'scatter' || mode.value === 'mixed')

  // Build the canonical layout once if either layer needs it.
  let layout = null
  if (showHex || mode.value === 'mixed') {
    layout = buildHoneycomb({
      pairs: data.pairs,
      mds_coords: data.mds_coords,
      clusters: data.clusters,
      k_clusters: data.k_clusters,
    })
  }

  if (showHex) {
    drawHoneycomb(svg, layout, W, H)
    if (mode.value === 'mixed') dimHexLayer(svg)
  }

  if (showDots) {
    if (mode.value === 'mixed') drawScatterAligned(svg, layout, W, H)
    else drawScatterRaw(svg, bounds, W, H)
  }

  // Heatmap layer — appended then re-positioned to the bottom of the
  // SVG child list so it sits behind cells / dots / cluster borders.
  drawTrainRefHeatmap(svg, refNorm, W, H)
  const heatmap = svg.querySelector('.train-ref-heatmap')
  if (heatmap && svg.firstChild && svg.firstChild !== heatmap) {
    svg.insertBefore(heatmap, svg.firstChild)
  }

  // Re-apply cell highlight after every redraw — the canonical renderer
  // rebuilds <polygon class="hex-cell"> from scratch, wiping any inline
  // opacity we set last time.
  applyCellHighlight()
}

// In mixed mode the hex aggregate reads as a backdrop; dots dominate.
// Drop hex fill alpha + soften cluster borders so dots pop.
function dimHexLayer(svg) {
  const cells = svg.querySelectorAll('polygon.hex-cell')
  cells.forEach(c => { c.style.fillOpacity = '0.55' })
  const borders = svg.querySelector('g.cluster-borders')
  if (borders) borders.style.opacity = '0.5'
  const stripes = svg.querySelector('g.hex-stripes')
  if (stripes) stripes.style.opacity = '0.5'
}

// Highlight the selected cell in hex-bearing modes by dimming all OTHER
// cells. No-op when nothing is selected or in pure scatter mode.
function applyCellHighlight() {
  const svg = svgRef.value
  if (!svg) return
  const cells = svg.querySelectorAll('polygon.hex-cell')
  const hexModeActive = mode.value === 'honeycomb' || mode.value === 'mixed'
  const isCellSel = hexModeActive
                    && selected.value?.kind === 'cell'
                    && selected.value.id != null
  cells.forEach(c => {
    if (!isCellSel) {
      c.style.opacity = ''
      c.style.stroke = ''
      c.style.strokeWidth = ''
      return
    }
    if (String(c.getAttribute('data-cell-id')) === String(selected.value.id)) {
      c.style.opacity = '1'
      c.style.stroke = '#1a1a1a'
      c.style.strokeWidth = '1.8'
    } else {
      c.style.opacity = '0.18'
      c.style.stroke = ''
      c.style.strokeWidth = ''
    }
  })
  const borders = svg.querySelector('g.cluster-borders')
  const stripes = svg.querySelector('g.hex-stripes')
  for (const g of [borders, stripes]) {
    if (g) g.style.opacity = isCellSel ? '0.25' : ''
  }
}

// Shared coordinate transform — must match the canonical renderer
// so all three layers (heatmap, scatter dots, hex cells) share one
// pixel space.
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
    scale, offsetX, offsetY,
  }
}

function drawTrainRefHeatmap(svg, refNorm, W, H) {
  if (!refNorm || refNorm.length < 5) return
  const t = pxTransform(W, H)
  const screen = refNorm.map(([cx, cy]) => [t.x(cx), t.y(cy)])
  const contours = d3.contourDensity()
    .x(p => p[0]).y(p => p[1])
    .size([W, H])
    .bandwidth(20)
    .thresholds(8)(screen)
  const cMax = d3.max(contours, c => c.value) || 1
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

function drawHoneycomb(svg, layout, W, H) {
  const opts = {
    width: W, height: H, marginPx: MARGIN_PX,
    colorBy: colorMode.value,
    showStripes: colorMode.value === 'gap',
  }
  renderHoneycomb(svg, layout, opts)
}

function onCanonicalCellClick(ev) {
  // Respond when ANY hex layer is active (honeycomb or mixed).
  if (mode.value === 'scatter' || !data) return
  const cell = ev.detail || {}
  const pairIds = cell.pairIds || []
  const pairs = pairIds.map(i => pairPayload(data.pairs[i], i)).filter(Boolean)
  if (!pairs.length) {
    bus.emit('hex-clear')
    selected.value = null
    applyCellHighlight()
    return
  }
  bus.emit('hex-select', { binKey: `cell:${cell.id}`, pairs })
  selected.value = { kind: 'cell', id: cell.id }
  applyCellHighlight()
}
function onCanonicalCellHover(_ev) { /* not wired into linked highlights */ }

// ──────────────────────────────────────────────────────────────────────
// Two scatter shapers
//   shapeRawScatter   → raw normalised mds_coords[i]. Used in pure
//                       'scatter' mode where the user wants to see the
//                       embedding the model actually learned.
//   shapeCellScatter  → packer cell positions + jitter. Used in 'mixed'
//                       mode so dots sit inside their hex cells.
// ──────────────────────────────────────────────────────────────────────
function _hashJitter(seed, idx, scale = 0.6) {
  const a = ((seed * 1103515245 + idx * 12345) >>> 0) / 0xffffffff
  const b = ((seed * 1664525 + idx * 1013904223) >>> 0) / 0xffffffff
  const ang = a * Math.PI * 2
  const r = Math.sqrt(b) * scale
  return [Math.cos(ang) * r, Math.sin(ang) * r]
}

function _topKPerHusband(out) {
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

function shapeCellScatter(layout) {
  const out = []
  const cells = layout?.cells || []
  const hexR = layout?.meta?.hexRadius ?? 0.04
  for (const cell of cells) {
    const ids = cell.pairIds || []
    if (!ids.length) continue
    let i = 0
    for (const pid of ids) {
      const p = data.pairs[pid]
      if (!p) { i++; continue }
      if (acceptedSet.value.has(`${p.husband_id}|${p.wife_id}`)) { i++; continue }
      const [jx, jy] = ids.length > 1 ? _hashJitter(cell.id, i, hexR * 0.6) : [0, 0]
      out.push({
        id: pid,
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
  return _topKPerHusband(out)
}

function shapeRawScatter(bounds) {
  const out = []
  const mds = data.mds_coords || []
  const pairs = data.pairs || []
  for (let i = 0; i < pairs.length; i++) {
    const p = pairs[i]
    if (!p) continue
    if (acceptedSet.value.has(`${p.husband_id}|${p.wife_id}`)) continue
    const c = mds[i] || [(bounds.xMin + bounds.xMax) / 2, (bounds.yMin + bounds.yMax) / 2]
    out.push({
      id: i,
      x: Math.max(0, Math.min(1, (c[0] - bounds.xMin) / bounds.xRange)),
      y: Math.max(0, Math.min(1, (c[1] - bounds.yMin) / bounds.yRange)),
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
      cluster: data?.clusters?.[i],
    })
  }
  return _topKPerHusband(out)
}

// Diverging score-gap palette — anchors at ±2 (raw HGT logit-gap units).
function gapColor(g) {
  const v = Math.max(-2, Math.min(2, g ?? 0))
  if (v <= 0) return d3.interpolateRgb('#993c1d', '#f5f1e8')((v + 2) / 2)
  return d3.interpolateRgb('#f5f1e8', '#0f6e56')(v / 2)
}
// Sequential HGT-score palette (GT-free). Anchors at cohort min/max
// computed once per draw and stashed on a closure-scoped object below.
let _scoreScale = null
function scoreColor(s) {
  if (!_scoreScale) return '#cfcfcf'
  const t = _scoreScale.range > 0 ? (s - _scoreScale.min) / _scoreScale.range : 0.5
  return d3.interpolateRgb('#f1ecdf', '#3a6a8a')(Math.max(0, Math.min(1, t)))
}
function dotColor(p) {
  return colorMode.value === 'score' ? scoreColor(p.raw_score) : gapColor(p.score_gap)
}

function _renderDots(svg, points, W, H) {
  const t = pxTransform(W, H)
  if (colorMode.value === 'score' && points.length) {
    let mn = Infinity, mx = -Infinity
    for (const p of points) { if (p.raw_score < mn) mn = p.raw_score; if (p.raw_score > mx) mx = p.raw_score }
    _scoreScale = { min: mn, max: mx, range: mx - mn }
  } else {
    _scoreScale = null
  }
  const root = d3.select(svg).append('g').attr('class', 'scatter')
  root.selectAll('circle').data(points).enter().append('circle')
    .attr('cx', p => t.x(p.x)).attr('cy', p => t.y(p.y))
    .attr('r', p => p.pair_type === 'pred' ? 2.4 : 3.2)
    .attr('fill', p => dotColor(p))
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

function drawScatterRaw(svg, bounds, W, H) {
  _renderDots(svg, shapeRawScatter(bounds), W, H)
}
function drawScatterAligned(svg, layout, W, H) {
  _renderDots(svg, shapeCellScatter(layout), W, H)
}

function attachLasso(root, t, W, H, points) {
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
  const t = event && event.target
  if (t && t !== svgRef.value) return
  if (selected.value) {
    selected.value = null
    bus.emit('hex-clear')
    applyCellHighlight()
  }
}

watch(() => `${appState.year}|${appState.ablation}`, () => { load() })

function onAccepted(evt) {
  if (!evt || evt.husband_id == null || evt.wife_id == null) return
  acceptedSet.value.add(`${evt.husband_id}|${evt.wife_id}`)
  draw()
}

// Re-show the (h, w) dot when an accept is rolled back upstream.
function onRestored(evt) {
  if (!evt || evt.husband_id == null || evt.wife_id == null) return
  acceptedSet.value.delete(`${evt.husband_id}|${evt.wife_id}`)
  draw()
}

function onExternalClear() {
  if (selected.value) {
    selected.value = null
    applyCellHighlight()
  }
}

onMounted(() => {
  load()
  window.addEventListener('resize', resizeHandler)
  bus.on('panel-resized', onPanelResized)
  bus.on('match-accepted', onAccepted)
  bus.on('match-restored', onRestored)
  bus.on('hex-clear', onExternalClear)
  if (svgRef.value) {
    svgRef.value.addEventListener('cell-clicked', onCanonicalCellClick)
    svgRef.value.addEventListener('cell-hovered', onCanonicalCellHover)
  }
})
onUnmounted(() => {
  window.removeEventListener('resize', resizeHandler)
  bus.off('panel-resized', onPanelResized)
  bus.off('match-accepted', onAccepted)
  bus.off('match-restored', onRestored)
  bus.off('hex-clear', onExternalClear)
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
.color-mode-btn {
  font-weight: 600;
  background: #eef3f7;
  border-color: #5a7a90;
  color: #1a1a1a;
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
    .ramp.seq-ramp {
      background: linear-gradient(to right, #f1ecdf 0%, #3a6a8a 100%);
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
