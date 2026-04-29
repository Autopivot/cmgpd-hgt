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

      <!-- Legend (collapsible) -->
      <div class="legend" :class="{ collapsed: !legendOpen }">
        <div class="legend-head" @click="legendOpen = !legendOpen">
          <span class="caret">{{ legendOpen ? '▾' : '▸' }}</span>
          <span class="tiny">legend</span>
        </div>
        <div v-if="legendOpen" class="legend-body">
          <div class="legend-section">
            <div class="legend-row"><span class="dot" style="background:#0f6e56"></span><span class="tiny">husband (focal)</span></div>
            <div class="legend-row"><span class="dot" style="background:#d4a85d;border:1px solid #1a1a1a"></span><span class="tiny">candidate wife</span></div>
            <div class="legend-row"><span class="dot small" style="background:#cfcfcf"></span><span class="tiny">kin (parent / child / sibling)</span></div>
          </div>
          <div class="legend-section">
            <div class="legend-row"><svg width="28" height="6"><line x1="2" y1="3" x2="26" y2="3" stroke="#666" stroke-width="1"/></svg><span class="tiny">paternal (r_fs / r_fd)</span></div>
            <div class="legend-row"><svg width="28" height="6"><line x1="2" y1="3" x2="26" y2="3" stroke="#666" stroke-width="1" stroke-dasharray="3 2"/></svg><span class="tiny">maternal (r_ms / r_md)</span></div>
            <div class="legend-row"><svg width="28" height="6"><line x1="2" y1="3" x2="26" y2="3" stroke="#888" stroke-width="1" stroke-dasharray="1 2"/></svg><span class="tiny">sibling (r_sib)</span></div>
            <div class="legend-row"><svg width="28" height="6"><line x1="2" y1="3" x2="26" y2="3" stroke="#c97a5a" stroke-width="1.6" stroke-dasharray="5 4"/></svg><span class="tiny">potential marriage</span></div>
            <div class="legend-row"><svg width="28" height="6"><line x1="2" y1="3" x2="26" y2="3" stroke="#993c1d" stroke-width="2"/></svg><span class="tiny">accepted marriage (click for SEAL)</span></div>
          </div>
        </div>
      </div>

      <!-- SEAL motif subwindow: opens on r_hw edge click -->
      <div v-if="sealOpen" class="seal-popover" @click.self="sealOpen = false">
        <div class="seal-card">
          <div class="seal-head">
            <span class="tiny muted">SEAL motif · {{ sealData?.husband_id }} ↔ {{ sealData?.wife_id }}</span>
            <span v-if="sealData" class="motif-tag" :class="'motif-' + sealData.motif_id">
              {{ sealData.motif_label || sealData.motif_id || '—' }}
            </span>
            <button class="popup-close" @click="sealOpen = false">×</button>
          </div>
          <div class="seal-body">
            <svg v-if="sealData" ref="sealSvgRef" class="seal-canvas"></svg>
            <div v-else class="muted tiny" style="padding:12px">loading…</div>
            <div v-if="sealData" class="seal-meta tiny muted">
              k = {{ sealData.drnl_radius }} · {{ sealData.nodes?.length || 0 }} nodes ·
              {{ sealData.edges?.length || 0 }} edges ·
              <span v-if="sealStub" style="color:#993c1d">(stub data — see seal_loader.py docstring for real-data contract)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'
import * as d3 from 'd3'
import bus from '../utils/eventbus.js'

// ── Inline API client (Unit 2's helpers will replace these when PR #16
// lands on the same base; until then this keeps the component self-
// contained and reviewer-replayable). ────────────────────────────────────
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
async function getSealSubgraph(husband_id, wife_id) {
  if (!husband_id || !wife_id) return null
  try {
    const r = await http.get(`/seal/${encodeURIComponent(husband_id)}/${encodeURIComponent(wife_id)}`)
    return r.data
  } catch {
    return null
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

// ── SEAL motif sub-window state ─────────────────────────────────────────
const sealOpen = ref(false)
const sealData = ref(null)        // schema v1 from /api/seal/{h}/{w}
const sealStub = ref(true)        // toggled false once a non-stub backend ships
const sealSvgRef = ref(null)
let sealSimulation = null

// ── Legend collapsible state ────────────────────────────────────────────
const legendOpen = ref(true)

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
  r_fs: { dash: null,    color: '#666',    width: 1 },
  r_fd: { dash: null,    color: '#666',    width: 1 },
  r_ms: { dash: '3 2',   color: '#666',    width: 1 },
  r_md: { dash: '3 2',   color: '#666',    width: 1 },
  r_sib: { dash: '1 2',  color: '#888',    width: 1 },
  r_hw: { dash: null,    color: '#993c1d', width: 2 },
  r_hw_potential: { dash: '5 4', color: '#c97a5a', width: 1.6 },
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
  // Add a potential (dashed) r_hw edge from husband to each candidate.
  // These materialise the moment V5 publishes its candidate set, so the
  // user immediately sees "these are the proposals on the table". On
  // accept, the matching potential edge is upgraded to a solid r_hw and
  // the others are removed.
  for (const cid of candidateIds.value) {
    if (cid === husband_id) continue
    if (out_nodes.some(n => n.id === cid) || out_nodes.some(n => n.id === husband_id)) {
      out_edges.push({ source: husband_id, target: cid, type: 'r_hw_potential' })
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
    .style('cursor', d => (d.type === 'r_hw' || d.type === 'r_hw_potential') ? 'pointer' : 'default')
    .on('click', (ev, d) => {
      if (d.type !== 'r_hw' && d.type !== 'r_hw_potential') return
      ev.stopPropagation()
      const sId = d.source.id || d.source
      const tId = d.target.id || d.target
      openSealSubgraph(sId, tId)
    })
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

// Fade level for non-winner egos on accept. 0.1 makes them "barely there"
// per the spec's "turns unnoticed" — strong enough to disappear from the
// reader's foreground while still hinting that more graph context exists.
const FADE_OPACITY = 0.1

function applyOpacityCascade(winnerWifeId) {
  const role = roleByNode.value
  function nodeOpacity(d) {
    const r = role.get(d.id)
    if (r === 'husband' || r === winnerWifeId || d.id === winnerWifeId) return 1.0
    return FADE_OPACITY
  }
  function edgeOpacity(d) {
    const sId = typeof d.source === 'object' ? d.source.id : d.source
    const tId = typeof d.target === 'object' ? d.target.id : d.target
    if (d.type === 'r_hw') return 1.0
    const sr = role.get(sId), tr = role.get(tId)
    const keep = (r) => r === 'husband' || r === winnerWifeId
    return (keep(sr) || keep(tr)) ? 1.0 : FADE_OPACITY
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

  // Upgrade the winner's potential edge to a solid r_hw, and drop the
  // other potential edges (those proposals are off the table).
  const eqEnd = (e, h, w) => {
    const sId = e.source?.id || e.source
    const tId = e.target?.id || e.target
    return sId === h && tId === w
  }
  const upgraded = []
  for (const e of edges.value) {
    if (e.type === 'r_hw_potential') {
      if (eqEnd(e, husband_id, wife_id)) {
        upgraded.push({ source: husband_id, target: wife_id, type: 'r_hw' })
      }
      // non-winner potentials are silently dropped here.
      continue
    }
    upgraded.push(e)
  }
  // If the winner's potential edge wasn't there (e.g. accept fired without
  // a prior cohort-context publish), insert a solid r_hw directly.
  if (!upgraded.some(e => e.type === 'r_hw' && eqEnd(e, husband_id, wife_id))) {
    upgraded.push({ source: husband_id, target: wife_id, type: 'r_hw' })
  }
  edges.value = upgraded

  renderGraph()  // re-bind data so the new edge gets a DOM node
  if (simulation) {
    try { simulation.alpha(0.2).restart() } catch (_) { /* not ready */ }
  }
  applyOpacityCascade(wife_id)
  activeAccept = { husband_id, wife_id }
}

function onMatchRestored({ husband_id, wife_id } = {}) {
  // Drop the solid r_hw for this pair; reinstate potentials for the full
  // candidate set so the panel returns to its pre-accept state.
  edges.value = edges.value.filter(e => {
    if (e.type !== 'r_hw') return true
    if (husband_id && wife_id) {
      const sId = e.source?.id || e.source
      const tId = e.target?.id || e.target
      return !(sId === husband_id && tId === wife_id)
    }
    return false
  })
  if (husbandId.value && candidateIds.value.length) {
    for (const cid of candidateIds.value) {
      if (cid === husbandId.value) continue
      const exists = edges.value.some(e => {
        const sId = e.source?.id || e.source
        const tId = e.target?.id || e.target
        return e.type === 'r_hw_potential' && sId === husbandId.value && tId === cid
      })
      if (!exists) {
        edges.value.push({ source: husbandId.value, target: cid, type: 'r_hw_potential' })
      }
    }
  }
  renderGraph()
  resetOpacity()
  if (simulation) {
    try { simulation.alpha(0.1).restart() } catch (_) { /* ignore */ }
  }
  activeAccept = null
}

// ── SEAL motif sub-window ────────────────────────────────────────────────
async function openSealSubgraph(husbandPid, wifePid) {
  // Click can come from either direction; the SEAL endpoint expects
  // (husband, wife). The husband-ego in our graph is the one whose role
  // is 'husband'; the other endpoint is the wife.
  let h = husbandPid, w = wifePid
  if (roleByNode.value.get(wifePid) === 'husband') { h = wifePid; w = husbandPid }
  sealOpen.value = true
  sealData.value = null
  const data = await getSealSubgraph(h, w)
  sealData.value = data
  sealStub.value = !!(data && data.version)   // STUB endpoint always sets version:'v1'
  // Render after Vue mounts the SVG element.
  setTimeout(() => renderSealSubgraph(), 50)
}

function renderSealSubgraph() {
  if (!sealSvgRef.value || !sealData.value) return
  const svg = d3.select(sealSvgRef.value)
  svg.selectAll('*').remove()
  const rect = sealSvgRef.value.getBoundingClientRect()
  const W = rect.width || 360
  const H = rect.height || 220
  svg.attr('viewBox', `0 0 ${W} ${H}`)

  const data = sealData.value
  const dataNodes = (data.nodes || []).map(n => ({
    ...n,
    radius: n.is_focal ? 9 : (n.role === 'anchor' ? 4 : 6),
  }))
  const dataEdges = (data.edges || []).map(e => ({ ...e }))

  if (sealSimulation) sealSimulation.stop()
  sealSimulation = d3.forceSimulation(dataNodes)
    .force('link', d3.forceLink(dataEdges).id(d => d.id).distance(45).strength(0.6))
    .force('charge', d3.forceManyBody().strength(-120))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collide', d3.forceCollide().radius(d => d.radius + 4))
    .alpha(0.7)

  const edgeSel = svg.append('g').attr('class', 'seal-edges').selectAll('line')
    .data(dataEdges).enter().append('line')
    .attr('stroke', d => d.is_motif_edge ? '#993c1d' : '#999')
    .attr('stroke-width', d => d.is_motif_edge ? 2 : 1)
    .attr('stroke-dasharray', d => {
      if (d.is_motif_edge) return null
      if (d.type === 'r_ms' || d.type === 'r_md') return '3 2'
      if (d.type === 'r_sib') return '1 2'
      return null
    })
    .attr('opacity', 0.85)

  const nodeSel = svg.append('g').attr('class', 'seal-nodes').selectAll('g')
    .data(dataNodes).enter().append('g')
  nodeSel.append('circle')
    .attr('r', d => d.radius)
    .attr('fill', d => {
      if (d.role === 'husband') return '#0f6e56'
      if (d.role === 'wife')    return '#d4a85d'
      if (d.role === 'anchor')  return '#cfcfcf'
      if (d.role === 'ancestor') return '#7a8b88'
      return '#a8a8a8'
    })
    .attr('stroke', d => d.is_focal ? '#1a1a1a' : 'none')
    .attr('stroke-width', d => d.is_focal ? 1.0 : 0)
  nodeSel.append('text')
    .attr('dy', d => d.radius + 11)
    .attr('text-anchor', 'middle')
    .style('font-size', '9px')
    .style('font-family', 'Monaco, monospace')
    .style('fill', '#444')
    .text(d => {
      if (d.id?.startsWith('anchor:')) return d.id.replace('anchor:', '')
      return d.id
    })
  nodeSel.append('title').text(d =>
    `${d.id} · role=${d.role} · drnl=${d.drnl_label} · sex=${d.sex || '?'}`)

  sealSimulation.on('tick', () => {
    edgeSel
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
    nodeSel.attr('transform', d => `translate(${d.x},${d.y})`)
  })
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

// Use viewport-fixed positioning so the popover overlays the entire app,
// not just V6's small panel cell — otherwise the card is clipped/invisible.
.seal-popover {
  position: fixed; inset: 0;
  background: rgba(20, 18, 14, 0.42);
  display: grid; place-items: center;
  z-index: 1000;
}
.seal-card {
  width: min(640px, 92vw); height: min(480px, 80vh);
  background: #fff;
  border: 1px solid #888; border-radius: 4px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.28);
  display: flex; flex-direction: column;
}
.seal-head {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; border-bottom: 1px solid #eee;
}
.seal-head .motif-tag {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: #d4e8df; color: #0a4a3a;
  font-family: Monaco, monospace;
  &.motif-none { background: #f0efe9; color: #888; }
}
.popup-close {
  margin-left: auto; background: transparent; border: none; cursor: pointer;
  font-size: 18px; color: #666; padding: 0 4px;
  &:hover { color: #1a1a1a; }
}
.seal-body { flex: 1 1 auto; display: flex; flex-direction: column; padding: 4px; min-height: 0; }
.seal-canvas { flex: 1 1 auto; width: 100%; }
.seal-meta { padding: 4px 6px; border-top: 1px solid #f0f0f0; }

// Legend — top-left of the canvas, semi-transparent so it doesn't hide
// nodes behind it. Collapses to a tiny header strip on click.
.legend {
  position: absolute; top: 6px; left: 6px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #d8d4c8; border-radius: 3px;
  padding: 4px 6px;
  font-family: Monaco, monospace;
  pointer-events: auto;
  user-select: none;
  max-width: 220px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.legend.collapsed { padding: 2px 6px; }
.legend-head {
  display: flex; align-items: center; gap: 4px;
  cursor: pointer;
  .caret { font-size: 9px; color: #888; }
}
.legend-body {
  display: flex; flex-direction: column; gap: 6px;
  margin-top: 4px;
}
.legend-section {
  display: flex; flex-direction: column; gap: 2px;
  padding-top: 2px;
  &:not(:first-child) { border-top: 1px dashed #e2ddd0; padding-top: 4px; }
}
.legend-row {
  display: flex; align-items: center; gap: 6px;
  line-height: 1.2;
  svg { flex: 0 0 auto; }
}
.dot {
  display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  flex: 0 0 auto;
  &.small { width: 7px; height: 7px; }
}
</style>
