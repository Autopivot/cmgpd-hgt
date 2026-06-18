<template>
  <div class="panel kinship">
    <div class="panel-head">
      <span>V6 · Kinship Neighbourhood</span>
      <span class="tiny muted">{{ headerChip }}</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v6')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body no-pad">
      <svg ref="svgRef" class="kinship-canvas">
        <defs>
          <marker id="arrow-fs" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="#666"/>
          </marker>
        </defs>
        <g ref="zoomLayerRef">
          <g ref="edgeLayerRef" class="edges"></g>
          <g ref="nodeLayerRef" class="nodes"></g>
        </g>
      </svg>
      <div v-if="!nodes.length" class="overlay muted tiny">
        load a husband in V5 (click in V3 / V4 / V2) to see his and the candidates' k=1 kinship neighbourhoods
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'
import * as d3 from 'd3'
import bus from '../utils/eventbus.js'

// ── Inline kinship API client (Unit 2's getKinshipMulti will replace this
// when PR #16 lands on the same base; until then this keeps the component
// self-contained and reviewer-replayable). ───────────────────────────────
const http = axios.create({ baseURL: '/api', timeout: 30000 })
async function getKinshipMulti(person_ids, k = 1) {
  if (!person_ids?.length) return { nodes: [], edges: [] }
  try {
    const r = await http.post('/kinship/multi', { person_ids, k })
    return r.data
  } catch {
    return { nodes: [], edges: [] }
  }
}

// ── Reactive state — Unit 5's accept-cascade reads these refs. ──────────
const nodes = ref([])              // [{ id, role, sex, ... }]
const edges = ref([])              // [{ source, target, type }]
const roleByNode = ref(new Map())  // pid -> 'husband' | candidate_id (winner-ego id)
let simulation = null              // d3-force simulation handle
let activeAccept = null            // { husband_id, wife_id }

const husbandId = ref(null)
const candidateIds = ref([])

const svgRef = ref(null)
const zoomLayerRef = ref(null)
const edgeLayerRef = ref(null)
const nodeLayerRef = ref(null)

const headerChip = computed(() => {
  if (!husbandId.value) return 'idle'
  return `kinship · k=1 · husband + ${candidateIds.value.length} candidates · ${nodes.value.length} nodes / ${edges.value.length} edges`
})

// ── Visual encoding constants ───────────────────────────────────────────
const NODE_FILL = {
  husband: '#0f6e56',     // sage green
  candidate: '#d4a85d',   // amber
  kin: '#cfcfcf',         // light grey
}
const NODE_RADIUS = { husband: 9, candidate: 8, kin: 5 }
const EDGE_STYLE = {
  r_fs: { dash: null,    color: '#666' },
  r_fd: { dash: null,    color: '#666' },
  r_ms: { dash: '3 2',   color: '#666' },
  r_md: { dash: '3 2',   color: '#666' },
  r_sib: { dash: '1 2',  color: '#888' },
  r_hw: { dash: null,    color: '#993c1d', width: 2 },
}

// ── Cohort-context listener: husband + top-K candidates ─────────────────
async function onCohortContext({ husband_id, candidate_ids } = {}) {
  husbandId.value = husband_id
  candidateIds.value = Array.isArray(candidate_ids) ? candidate_ids.slice() : []
  if (!husband_id) {
    nodes.value = []
    edges.value = []
    roleByNode.value = new Map()
    activeAccept = null
    renderGraph()
    return
  }
  const ids = [husband_id, ...candidateIds.value]
  // Fetch each ego separately so we can stamp `roleByNode` with the right
  // owning ego (husband vs candidate-XX). The /kinship/multi endpoint
  // dedupes nodes which loses ego provenance — single fetches preserve it.
  const egos = await Promise.all(
    ids.map(async pid => {
      try {
        const r = await http.get(`/kinship/${encodeURIComponent(pid)}`, { params: { k: 1 } })
        return { pid, data: r.data }
      } catch {
        return { pid, data: { focal_id: pid, nodes: [{ id: pid, role: 'focal' }], edges: [] } }
      }
    })
  )
  // Merge nodes deduped by id; if a node belongs to multiple egos the husband-ego wins.
  const seenNodes = new Map()
  const seenEdges = new Set()
  const role = new Map()
  const out_nodes = []
  const out_edges = []
  for (const { pid, data } of egos) {
    const isHusband = pid === husband_id
    for (const n of (data.nodes || [])) {
      const owningEgo = isHusband ? 'husband' : pid
      if (!seenNodes.has(n.id)) {
        seenNodes.set(n.id, true)
        const ownRole = (n.id === husband_id) ? 'husband'
                      : candidateIds.value.includes(n.id) ? 'candidate'
                      : 'kin'
        out_nodes.push({ id: n.id, sex: n.sex || '?', role: ownRole })
      }
      // Husband-ego wins ownership conflicts.
      if (!role.has(n.id) || owningEgo === 'husband') {
        role.set(n.id, owningEgo)
      }
    }
    for (const e of (data.edges || [])) {
      const k = `${e.source}|${e.target}|${e.type}`
      if (seenEdges.has(k)) continue
      seenEdges.add(k)
      out_edges.push({ source: e.source, target: e.target, type: e.type })
    }
  }
  nodes.value = out_nodes
  edges.value = out_edges
  roleByNode.value = role
  activeAccept = null
  renderGraph()
}

// ── d3-force rendering ──────────────────────────────────────────────────
function renderGraph() {
  if (!svgRef.value) return
  const svg = d3.select(svgRef.value)
  const rect = svgRef.value.getBoundingClientRect()
  const W = rect.width || 400
  const H = rect.height || 320

  svg.attr('viewBox', `0 0 ${W} ${H}`)

  // Re-attach zoom every render (idempotent).
  const zoomLayer = d3.select(zoomLayerRef.value)
  svg.call(d3.zoom().scaleExtent([0.3, 4]).on('zoom', (ev) => {
    zoomLayer.attr('transform', ev.transform)
  }))

  // Stop any previous simulation before swapping data.
  if (simulation) simulation.stop()

  if (!nodes.value.length) {
    d3.select(edgeLayerRef.value).selectAll('*').remove()
    d3.select(nodeLayerRef.value).selectAll('*').remove()
    return
  }

  // Mutable copies — d3-force annotates these in place with x, y, vx, vy.
  const dataNodes = nodes.value.map(n => ({ ...n }))
  const dataEdges = edges.value.map(e => ({ ...e }))

  simulation = d3.forceSimulation(dataNodes)
    .force('link', d3.forceLink(dataEdges).id(d => d.id).distance(30).strength(0.7))
    .force('charge', d3.forceManyBody().strength(-80))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collide', d3.forceCollide().radius(d => NODE_RADIUS[d.role] + 2))
    .alpha(0.6)

  // ── Edges ──
  const edgeSel = d3.select(edgeLayerRef.value)
    .selectAll('line.edge')
    .data(dataEdges, d => `${d.source.id || d.source}|${d.target.id || d.target}|${d.type}`)
  edgeSel.exit().remove()
  const edgeEnter = edgeSel.enter().append('line')
    .attr('class', 'edge')
    .attr('stroke', d => EDGE_STYLE[d.type]?.color || '#999')
    .attr('stroke-width', d => EDGE_STYLE[d.type]?.width || 1)
    .attr('stroke-dasharray', d => EDGE_STYLE[d.type]?.dash || null)
    .attr('opacity', 0.8)
  const edgeMerged = edgeEnter.merge(edgeSel)

  // ── Nodes ──
  const nodeSel = d3.select(nodeLayerRef.value)
    .selectAll('g.node')
    .data(dataNodes, d => d.id)
  nodeSel.exit().remove()
  const nodeEnter = nodeSel.enter().append('g')
    .attr('class', 'node')
    .attr('data-id', d => d.id)
  nodeEnter.append('circle')
    .attr('r', d => NODE_RADIUS[d.role] || 5)
    .attr('fill', d => NODE_FILL[d.role] || '#cfcfcf')
    .attr('stroke', d => d.role === 'candidate' ? '#1a1a1a' : (d.role === 'husband' ? '#1a1a1a' : 'none'))
    .attr('stroke-width', d => d.role === 'kin' ? 0 : 0.8)
  nodeEnter.append('title').text(d => `${d.id} · sex=${d.sex} · role=${d.role}`)
  const nodeMerged = nodeEnter.merge(nodeSel)

  // Drag — pin on release; double-click to release.
  const drag = d3.drag()
    .on('start', (ev, d) => {
      if (!ev.active) simulation.alphaTarget(0.3).restart()
      d.fx = d.x; d.fy = d.y
    })
    .on('drag', (ev, d) => { d.fx = ev.x; d.fy = ev.y })
    .on('end', (ev, d) => {
      if (!ev.active) simulation.alphaTarget(0)
      // Leave d.fx/fy set so the node stays pinned; double-click releases.
    })
  nodeMerged.call(drag)
  nodeMerged.on('dblclick', (ev, d) => { d.fx = null; d.fy = null; simulation.alpha(0.2).restart() })

  simulation.on('tick', () => {
    edgeMerged
      .attr('x1', d => d.source.x ?? 0)
      .attr('y1', d => d.source.y ?? 0)
      .attr('x2', d => d.target.x ?? 0)
      .attr('y2', d => d.target.y ?? 0)
    nodeMerged.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`)
  })
}

// ── Unit 5 — accept cascade (preserved from earlier landing) ────────────
function selectKinshipSvg() { return d3.select(svgRef.value) }

function applyOpacityCascade(winnerWifeId) {
  const role = roleByNode.value
  function nodeOpacity(d) {
    const r = role.get(d.id)
    if (r === 'husband' || r === winnerWifeId || d.id === winnerWifeId) return 1.0
    return 0.25
  }
  function edgeOpacity(d) {
    const sId = typeof d.source === 'object' ? d.source.id : d.source
    const tId = typeof d.target === 'object' ? d.target.id : d.target
    if (d.type === 'r_hw') return 1.0
    const sr = role.get(sId), tr = role.get(tId)
    const keep = (r) => r === 'husband' || r === winnerWifeId
    return (keep(sr) || keep(tr)) ? 1.0 : 0.25
  }
  const svg = selectKinshipSvg()
  if (svg.empty()) return
  svg.selectAll('g.nodes > g.node').transition().duration(200).style('opacity', nodeOpacity)
  svg.selectAll('g.edges > line.edge').transition().duration(200).style('opacity', edgeOpacity)
}

function resetOpacity() {
  const svg = selectKinshipSvg()
  if (svg.empty()) return
  svg.selectAll('g.nodes > g.node').transition().duration(200).style('opacity', 1.0)
  svg.selectAll('g.edges > line.edge').transition().duration(200).style('opacity', 1.0)
}

function ensureWifeNode(wifeId) {
  if (!nodes.value.some(n => n.id === wifeId)) {
    nodes.value.push({ id: wifeId, role: 'candidate', sex: '?', synthetic: true })
    roleByNode.value.set(wifeId, wifeId)
  }
}

function onMatchAccepted({ husband_id, wife_id } = {}) {
  if (!husband_id || !wife_id) return
  if (!nodes.value.some(n => n.id === husband_id)) {
    console.warn(`[V6 accept-cascade] husband_id ${husband_id} not in kinship graph; skipping`)
    return
  }
  if (activeAccept) {
    edges.value = edges.value.filter(e => e.type !== 'r_hw')
    resetOpacity()
  }
  ensureWifeNode(wife_id)
  if (!edges.value.some(e =>
    e.type === 'r_hw' &&
    (e.source === husband_id || e.source?.id === husband_id) &&
    (e.target === wife_id    || e.target?.id === wife_id))) {
    edges.value.push({ source: husband_id, target: wife_id, type: 'r_hw' })
  }
  renderGraph()  // re-bind data so the new edge gets a DOM node
  if (simulation) {
    try { simulation.alpha(0.2).restart() } catch (_) { /* not ready */ }
  }
  applyOpacityCascade(wife_id)
  activeAccept = { husband_id, wife_id }
}

function onMatchRestored({ husband_id, wife_id } = {}) {
  edges.value = edges.value.filter(e => {
    if (e.type !== 'r_hw') return true
    if (husband_id && wife_id) {
      const sId = e.source?.id || e.source
      const tId = e.target?.id || e.target
      return !(sId === husband_id && tId === wife_id)
    }
    return false
  })
  renderGraph()
  resetOpacity()
  if (simulation) {
    try { simulation.alpha(0.1).restart() } catch (_) { /* ignore */ }
  }
  activeAccept = null
}

let resizeRO = null

onMounted(() => {
  bus.on('cohort-context', onCohortContext)
  bus.on('match-accepted', onMatchAccepted)
  bus.on('match-restored', onMatchRestored)
  resizeRO = new ResizeObserver(() => renderGraph())
  if (svgRef.value) resizeRO.observe(svgRef.value)
})

onBeforeUnmount(() => {
  bus.off('cohort-context', onCohortContext)
  bus.off('match-accepted', onMatchAccepted)
  bus.off('match-restored', onMatchRestored)
  if (resizeRO) resizeRO.disconnect()
  if (simulation) simulation.stop()
})

defineExpose({ nodes, edges, roleByNode })
</script>

<style lang="less" scoped>
.kinship.panel { display: flex; flex-direction: column; }
.panel-body { position: relative; flex: 1 1 auto; min-height: 0; }
.kinship-canvas {
  width: 100%; height: 100%; display: block;
  background: #fbfaf6;
  cursor: grab;
  &:active { cursor: grabbing; }
}
.overlay {
  position: absolute; inset: 0; display: grid; place-items: center;
  text-align: center; padding: 16px; pointer-events: none;
  font-size: 11px; color: #888;
}
g.node { cursor: pointer; }
</style>
