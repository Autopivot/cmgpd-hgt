<template>
  <svg
    class="motif-glyph"
    :viewBox="`0 0 ${W} ${H}`"
    :width="W"
    :height="H"
    :aria-label="ariaLabel"
  >
    <template v-if="nodes.length">
      <!-- edges first so nodes draw on top -->
      <g class="edges">
        <line
          v-for="(e, i) in drawnEdges"
          :key="'e' + i"
          :x1="nodes[e.u].x"
          :y1="nodes[e.u].y"
          :x2="nodes[e.v].x"
          :y2="nodes[e.v].y"
          :stroke="e.color"
          :stroke-width="e.w"
          stroke-linecap="round"
          :opacity="0.85"
        >
          <title>{{ e.rel }}: {{ e.u }} ↔ {{ e.v }}</title>
        </line>
      </g>
      <g class="nodes">
        <template v-for="(n, i) in nodes" :key="'n' + i">
          <polygon
            v-if="n.isEndpoint"
            :points="starPoints(n.x, n.y, n.r * 1.15, n.r * 0.52, 5)"
            :fill="n.fill"
            :stroke="n.stroke"
            :stroke-width="n.strokeWidth"
          >
            <title>{{ n.tooltip }}</title>
          </polygon>
          <circle
            v-else
            :cx="n.x" :cy="n.y" :r="n.r"
            :fill="n.fill" :stroke="n.stroke" :stroke-width="n.strokeWidth"
          >
            <title>{{ n.tooltip }}</title>
          </circle>
        </template>
      </g>
    </template>
    <rect v-else x="2" y="2" :width="W - 4" :height="H - 4"
          fill="none" stroke="#bbb" stroke-dasharray="3 2" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  example: { type: Object, default: () => ({}) },
  size: { type: Number, default: 96 },
})

const W = computed(() => props.size)
const H = computed(() => Math.round(props.size * 0.75))

// src (husband) = red star, dst (wife) = orange star
const SRC_COLOR = '#e6194b'
const DST_COLOR = '#f58231'
const UNREACHABLE = '#cccccc'
// Viridis-style ramp for DRNL ≥ 2 (darker = structurally closer)
const DRNL_PALETTE = [
  '#440154', '#3b528b', '#21918c', '#5ec962',
  '#a0da39', '#fde725', '#ffbf00', '#ff7f00',
]
// Edge colors by relation. CMGPD-LN edge set: keeps r_fs/r_fd/r_ms/r_md
// distinguished, plus r_sib and r_hw, matching src/config.py.
const EDGE_COLOR = {
  r_hw:  '#e6194b',
  r_fs:  '#4363d8',
  r_fd:  '#3a86ff',
  r_ms:  '#911eb4',
  r_md:  '#a64ca6',
  r_sib: '#3cb44b',
  r_hh:  '#888780',
  r_cb:  '#bbb',
}

function drnlColor(label, isSrc, isDst) {
  if (isSrc) return SRC_COLOR
  if (isDst) return DST_COLOR
  if (label === 0) return UNREACHABLE
  if (label === 1) return '#800080'
  const idx = Math.min(label - 2, DRNL_PALETTE.length - 1)
  return DRNL_PALETTE[idx]
}

const srcLocal = computed(() => props.example?.src_local ?? -1)
const dstLocal = computed(() => props.example?.dst_local ?? -1)

const nodes = computed(() => {
  const ex = props.example || {}
  const n = ex.num_nodes || 0
  if (!n) return []
  const labels = ex.drnl_labels || []
  const cx = W.value / 2
  const cy = H.value / 2
  const r = Math.min(W.value, H.value) / 2 - 8
  const nodeR = n <= 3 ? 4.5 : n <= 6 ? 3.8 : 3.2
  const out = []
  for (let i = 0; i < n; i++) {
    let x, y
    if (n === 1) { x = cx; y = cy }
    else if (n === 2) { x = cx + (i === 0 ? -r : r); y = cy }
    else {
      const a = (2 * Math.PI * i) / n - Math.PI / 2
      x = cx + r * Math.cos(a)
      y = cy + r * Math.sin(a)
    }
    const isSrc = i === srcLocal.value
    const isDst = i === dstLocal.value
    const lab = labels[i] ?? 0
    const role = isSrc ? 'src (husband)' : isDst ? 'dst (wife)' : 'context'
    out.push({
      x, y, r: nodeR,
      isEndpoint: isSrc || isDst,
      fill: drnlColor(lab, isSrc, isDst),
      stroke: isSrc || isDst ? '#2b2622' : '#4a4a4a',
      strokeWidth: isSrc || isDst ? 1.0 : 0.5,
      tooltip: `#${i} · DRNL=${lab} · ${role}`,
    })
  }
  return out
})

const drawnEdges = computed(() => {
  const ex = props.example || {}
  const raw = Array.isArray(ex.edges) ? ex.edges : []
  const etypes = Array.isArray(ex.edge_types) ? ex.edge_types : []
  const seen = new Set()
  const out = []
  for (let i = 0; i < raw.length; i++) {
    const e = raw[i]
    if (!Array.isArray(e) || e.length < 2) continue
    const u = e[0], v = e[1]
    const key = u < v ? `${u}-${v}` : `${v}-${u}`
    if (seen.has(key)) continue
    seen.add(key)
    const rel = etypes[i] || '?'
    out.push({
      u, v, rel,
      color: EDGE_COLOR[rel] || '#888',
      w: rel === '?' ? 0.9 : 1.4,
    })
  }
  return out
})

function starPoints(cx, cy, rOuter, rInner, spikes) {
  const pts = []
  const step = Math.PI / spikes
  let rot = -Math.PI / 2
  for (let i = 0; i < spikes; i++) {
    pts.push(`${(cx + Math.cos(rot) * rOuter).toFixed(2)},${(cy + Math.sin(rot) * rOuter).toFixed(2)}`)
    rot += step
    pts.push(`${(cx + Math.cos(rot) * rInner).toFixed(2)},${(cy + Math.sin(rot) * rInner).toFixed(2)}`)
    rot += step
  }
  return pts.join(' ')
}

const ariaLabel = computed(() => {
  const ex = props.example || {}
  return `motif glyph |V|=${ex.num_nodes ?? 0} |E|=${(ex.edges || []).length}`
})
</script>

<style lang="less" scoped>
.motif-glyph {
  display: block;
  background: #fdfaf3;
  border: 1px solid #e3dcc9;
  border-radius: 3px;
  flex: 0 0 auto;
}
</style>
