<template>
  <svg
    class="motif-mini-glyph"
    :width="size"
    :height="size"
    :viewBox="`0 0 ${size} ${size}`"
    xmlns="http://www.w3.org/2000/svg"
  >
    <!-- edges -->
    <g class="edges">
      <line
        v-for="(e, i) in layout.edges"
        :key="`e-${i}`"
        :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
        :stroke="edgeColor(e.relation)"
        stroke-width="1.4"
      />
      <text
        v-for="(e, i) in layout.edges"
        :key="`l-${i}`"
        :x="(e.x1 + e.x2) / 2"
        :y="(e.y1 + e.y2) / 2 - 3"
        text-anchor="middle"
        class="edge-label"
        :fill="edgeColor(e.relation)"
      >{{ e.relation }}</text>
    </g>
    <!-- nodes -->
    <g class="nodes">
      <template v-for="(n, i) in layout.nodes" :key="`n-${i}`">
        <polygon
          v-if="n.kind === 'h'"
          :points="starPoints(n.x, n.y, 6.2, 2.6, 5)"
          fill="#c7382e"
          stroke="#7a1f17"
          stroke-width="0.7"
        />
        <polygon
          v-else-if="n.kind === 'w'"
          :points="starPoints(n.x, n.y, 6.2, 2.6, 5)"
          fill="#e98c2c"
          stroke="#8a4a13"
          stroke-width="0.7"
        />
        <circle
          v-else
          :cx="n.x" :cy="n.y" r="3.6"
          fill="#cbcbc6"
          stroke="#6f6f6a"
          stroke-width="0.7"
        />
        <text
          :x="n.x" :y="n.y + 14"
          text-anchor="middle"
          class="node-label"
        >{{ n.label }}</text>
      </template>
    </g>
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  motif: { type: Object, required: true },  // { id, relations:[], length:int }
  size:  { type: Number, default: 72 },
})

function edgeColor(rel) {
  if (!rel) return '#888'
  if (rel.startsWith('r_f')) return '#3a6a8a'
  if (rel.startsWith('r_m')) return '#993c1d'
  if (rel === 'r_sib')       return '#d4a85d'
  return '#888'
}

function starPoints(cx, cy, rOuter, rInner, points) {
  const step = Math.PI / points
  const pts = []
  let angle = -Math.PI / 2
  for (let i = 0; i < points * 2; i++) {
    const r = (i % 2 === 0) ? rOuter : rInner
    pts.push(`${(cx + Math.cos(angle) * r).toFixed(2)},${(cy + Math.sin(angle) * r).toFixed(2)}`)
    angle += step
  }
  return pts.join(' ')
}

const layout = computed(() => {
  const S = props.size
  const cx = S / 2
  const relations = props.motif?.relations || []
  const length = props.motif?.length ?? relations.length

  const padX = 10
  const yMid = S / 2
  const yTop = S * 0.30
  const yBot = S * 0.66

  // length 1: h -- w
  if (length <= 1) {
    const rel = relations[0] || ''
    return {
      nodes: [
        { x: padX + 6,    y: yMid, kind: 'h', label: 'h' },
        { x: S - padX - 6, y: yMid, kind: 'w', label: 'w' },
      ],
      edges: [{ x1: padX + 6, y1: yMid, x2: S - padX - 6, y2: yMid, relation: rel }],
    }
  }

  // length 2: detect "Y" shape (anchor-down) vs chain.
  // Y shape: relations like ['r_fs','r_fd'] — both edges originate from a
  // shared anchor reaching down to h and w. Heuristic: same prefix family
  // (r_f.. + r_f.. or r_m.. + r_m..) AND not both r_sib.
  if (length === 2) {
    const [r1, r2] = relations
    const isY = (
      (r1?.startsWith('r_f') && r2?.startsWith('r_f')) ||
      (r1?.startsWith('r_m') && r2?.startsWith('r_m'))
    ) && !(r1 === 'r_sib' && r2 === 'r_sib')

    if (isY) {
      const anchor = { x: cx, y: yTop, kind: 'mid', label: 'A' }
      const h = { x: padX + 6, y: yBot, kind: 'h', label: 'h' }
      const w = { x: S - padX - 6, y: yBot, kind: 'w', label: 'w' }
      return {
        nodes: [anchor, h, w],
        edges: [
          { x1: anchor.x, y1: anchor.y, x2: h.x, y2: h.y, relation: r1 },
          { x1: anchor.x, y1: anchor.y, x2: w.x, y2: w.y, relation: r2 },
        ],
      }
    }
    // chain h - m - w
    const h = { x: padX + 6, y: yMid, kind: 'h', label: 'h' }
    const m = { x: cx, y: yMid, kind: 'mid', label: 'm' }
    const w = { x: S - padX - 6, y: yMid, kind: 'w', label: 'w' }
    return {
      nodes: [h, m, w],
      edges: [
        { x1: h.x, y1: h.y, x2: m.x, y2: m.y, relation: r1 },
        { x1: m.x, y1: m.y, x2: w.x, y2: w.y, relation: r2 },
      ],
    }
  }

  // length >= 3: horizontal chain of (length+1) nodes.
  const n = length + 1
  const usable = S - padX * 2 - 12
  const step = usable / (n - 1)
  const xs = Array.from({ length: n }, (_, i) => padX + 6 + i * step)
  const nodes = xs.map((x, i) => {
    if (i === 0)       return { x, y: yMid, kind: 'h', label: 'h' }
    if (i === n - 1)   return { x, y: yMid, kind: 'w', label: 'w' }
    return { x, y: yMid, kind: 'mid', label: `n${i}` }
  })
  const edges = []
  for (let i = 0; i < n - 1; i++) {
    edges.push({
      x1: nodes[i].x, y1: nodes[i].y,
      x2: nodes[i + 1].x, y2: nodes[i + 1].y,
      relation: relations[i] || '',
    })
  }
  return { nodes, edges }
})
</script>

<style lang="less" scoped>
.motif-mini-glyph {
  display: block;
  background: #fbf9f3;
  border-radius: 3px;
}
.edge-label {
  font-size: 7px;
  font-family: Monaco, Menlo, monospace;
  pointer-events: none;
}
.node-label {
  font-size: 7px;
  fill: #444;
  font-family: Monaco, Menlo, monospace;
  pointer-events: none;
}
</style>
