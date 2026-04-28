<template>
  <div class="panel">
    <div class="panel-head">
      <span>V6 · Kinship neighbourhood</span>
      <span class="tiny muted chip">{{ headerChip }}</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v6')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body">
      <div ref="container" class="canvas-wrap">
        <svg ref="svgEl" class="kinship-svg">
          <g ref="rootG">
            <g ref="edgeG" class="edges"></g>
            <g ref="nodeG" class="nodes"></g>
          </g>
        </svg>
        <div v-if="empty" class="placeholder tiny muted">
          Click a hex in V3 → load a husband in V4 → hit ▶ arena in V5
          to populate the kinship subgraph here.
        </div>
        <div v-if="tooltip.visible" class="tooltip" :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
          <div><strong>{{ tooltip.id }}</strong></div>
          <div class="tiny">sex: {{ tooltip.sex }} · role: {{ tooltip.role }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, defineExpose } from 'vue'
import * as d3 from 'd3'
import bus from '../utils/eventbus.js'
import { getKinshipMulti } from '../api/client.js'

// ── refs / state ──────────────────────────────────────────────────────
const container = ref(null)
const svgEl = ref(null)
const rootG = ref(null)
const edgeG = ref(null)
const nodeG = ref(null)

const empty = ref(true)
const tooltip = reactive({ visible: false, x: 0, y: 0, id: '', sex: '?', role: '' })

// d3 simulation state — kept as plain (non-reactive) module-locals so Vue
// doesn't deeply proxy d3's internal force objects.
let nodes = []          // [{id, sex, role, x, y, fx, fy}]
let edges = []          // [{source, target, type}]
let roleByNode = {}     // id → 'husband' | 'candidate' | 'kin'
let simulation = null
let zoom = null
let resizeObs = null

const headerChip = ref('kinship · k=1 · awaiting cohort')

// ── d3 setup ──────────────────────────────────────────────────────────
function getSize() {
  const el = container.value
  if (!el) return [400, 300]
  const w = el.clientWidth || 400
  const h = el.clientHeight || 300
  return [w, h]
}

function setupZoom() {
  const svg = d3.select(svgEl.value)
  const g = d3.select(rootG.value)
  zoom = d3.zoom()
    .scaleExtent([0.3, 4])
    .on('zoom', (event) => { g.attr('transform', event.transform) })
  svg.call(zoom)
  svg.on('dblclick.zoom', null)  // disable default dbl-click zoom
}

function setupSim() {
  const [w, h] = getSize()
  simulation = d3.forceSimulation()
    .force('link', d3.forceLink().id(d => d.id).distance(30).strength(0.6))
    .force('charge', d3.forceManyBody().strength(-80))
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force('collide', d3.forceCollide().radius(d => radiusFor(d) + 2))
    .on('tick', tick)
}

function radiusFor(d) {
  const role = roleByNode[d.id] || d.role || 'kin'
  if (role === 'husband') return 9
  if (role === 'candidate') return 8
  return 5
}

function fillFor(d) {
  const role = roleByNode[d.id] || d.role || 'kin'
  if (role === 'husband') return '#1f8a5a'    // green
  if (role === 'candidate') return '#e0a020'  // amber
  return '#bdbdbd'                             // grey
}

function strokeFor(d) {
  const role = roleByNode[d.id] || d.role || 'kin'
  if (role === 'candidate') return '#7a5300'   // ring
  return 'none'
}

function edgeStyle(e) {
  // returns [strokeColor, strokeDasharray, strokeWidth]
  switch (e.type) {
    case 'r_fs':
    case 'r_fd':
      return ['#888', null, 1]
    case 'r_ms':
    case 'r_md':
      return ['#888', '4 3', 1]
    case 'r_sib':
      return ['#aaa', '1 3', 1]
    case 'r_hw':
      return ['#c0392b', null, 2]
    default:
      return ['#bbb', null, 1]
  }
}

// ── render ───────────────────────────────────────────────────────────
function tick() {
  d3.select(edgeG.value).selectAll('line.edge')
    .attr('x1', d => (d.source.x ?? 0))
    .attr('y1', d => (d.source.y ?? 0))
    .attr('x2', d => (d.target.x ?? 0))
    .attr('y2', d => (d.target.y ?? 0))
  d3.select(nodeG.value).selectAll('circle.node')
    .attr('cx', d => d.x)
    .attr('cy', d => d.y)
}

function edgeKey(e) {
  const s = typeof e.source === 'object' ? e.source.id : e.source
  const t = typeof e.target === 'object' ? e.target.id : e.target
  return `${s}-${t}-${e.type}`
}

function render() {
  const edgeSel = d3.select(edgeG.value).selectAll('line.edge').data(edges, edgeKey)
  edgeSel.exit().remove()
  edgeSel.enter().append('line')
    .attr('class', 'edge')
    .merge(edgeSel)
    .attr('stroke', e => edgeStyle(e)[0])
    .attr('stroke-dasharray', e => edgeStyle(e)[1])
    .attr('stroke-width', e => edgeStyle(e)[2])
    .attr('opacity', 0.9)

  const nodeSel = d3.select(nodeG.value).selectAll('circle.node')
    .data(nodes, d => d.id)
  nodeSel.exit().remove()
  const enter = nodeSel.enter().append('circle')
    .attr('class', 'node')
    .call(d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x; d.fy = d.y
      })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        // pin on release: keep fx/fy. Double-click clears.
      }))
    .on('dblclick', (_event, d) => { d.fx = null; d.fy = null; simulation.alphaTarget(0.1).restart(); setTimeout(() => simulation.alphaTarget(0), 300) })
    .on('mouseover', (event, d) => {
      tooltip.visible = true
      tooltip.id = d.id
      tooltip.sex = d.sex || '?'
      tooltip.role = roleByNode[d.id] || d.role || 'kin'
      const rect = container.value.getBoundingClientRect()
      tooltip.x = event.clientX - rect.left + 8
      tooltip.y = event.clientY - rect.top + 8
    })
    .on('mouseout', () => { tooltip.visible = false })
  enter.merge(nodeSel)
    .attr('r', radiusFor)
    .attr('fill', fillFor)
    .attr('stroke', strokeFor)
    .attr('stroke-width', d => (roleByNode[d.id] === 'candidate' ? 2 : 0))

  simulation.nodes(nodes)
  simulation.force('link').links(edges)
  simulation.alpha(0.3).restart()
}

// ── data flow ────────────────────────────────────────────────────────
function buildRoleMap(payload, husbandId, candidateIds) {
  const cset = new Set(candidateIds || [])
  const m = {}
  for (const n of (payload.nodes || [])) m[n.id] = 'kin'
  for (const c of cset) m[c] = 'candidate'
  if (husbandId) m[husbandId] = 'husband'  // husband wins over candidate
  return m
}

async function refreshFromCohort(ctx) {
  const husbandId = ctx?.husband_id || null
  const candidateIds = (ctx?.candidate_ids || []).filter(c => c && c !== husbandId)
  const ids = husbandId ? [husbandId, ...candidateIds] : []

  if (ids.length === 0) {
    nodes = []; edges = []; roleByNode = {}
    empty.value = true
    headerChip.value = 'kinship · k=1 · awaiting cohort'
    render()
    return
  }

  const sub = await getKinshipMulti(ids, 1)
  roleByNode = buildRoleMap(sub, husbandId, candidateIds)

  // Preserve positions of nodes that survive the refresh — keeps warm restarts smooth.
  const prevPos = new Map(nodes.map(n => [n.id, { x: n.x, y: n.y, fx: n.fx, fy: n.fy }]))
  nodes = (sub.nodes || []).map(n => ({ ...n, ...(prevPos.get(n.id) || {}) }))
  edges = (sub.edges || []).map(e => ({ source: e.source, target: e.target, type: e.type }))

  empty.value = nodes.length === 0
  headerChip.value = `kinship · k=1 · husband + ${candidateIds.length} candidates · ${nodes.length} nodes / ${edges.length} edges`
  render()
}

// ── lifecycle ────────────────────────────────────────────────────────
function onResize() {
  if (!simulation) return
  const [w, h] = getSize()
  simulation.force('center', d3.forceCenter(w / 2, h / 2))
  simulation.alpha(0.1).restart()
}

const cohortHandler = (ctx) => { refreshFromCohort(ctx) }

onMounted(() => {
  setupZoom()
  setupSim()
  bus.on('cohort-context', cohortHandler)
  if (typeof ResizeObserver !== 'undefined') {
    resizeObs = new ResizeObserver(onResize)
    resizeObs.observe(container.value)
  }
  // No data yet — show placeholder.
  render()
})

onBeforeUnmount(() => {
  bus.off('cohort-context', cohortHandler)
  if (simulation) simulation.stop()
  if (resizeObs) resizeObs.disconnect()
})

// Expose internals so Unit 5 (accept-cascade) can mutate edges + opacity.
defineExpose({
  // live arrays — mutate then call render()
  get nodes() { return nodes },
  get edges() { return edges },
  get simulation() { return simulation },
  get roleByNode() { return roleByNode },
  render,
})
</script>

<style lang="less" scoped>
.panel-head .chip { margin-left: 8px; }
.canvas-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 220px;
  overflow: hidden;
  background: #faf8f2;
  border-radius: 3px;
}
.kinship-svg {
  width: 100%;
  height: 100%;
  display: block;
  cursor: grab;
  &:active { cursor: grabbing; }
}
.placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 0 16px;
  pointer-events: none;
}
.tooltip {
  position: absolute;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #d0c8b0;
  border-radius: 3px;
  padding: 4px 6px;
  font-size: 10px;
  pointer-events: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
  z-index: 10;
}
:deep(circle.node) { cursor: grab; }
:deep(circle.node:active) { cursor: grabbing; }
</style>
