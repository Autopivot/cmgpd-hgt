<template>
  <div class="panel">
    <div class="panel-head">
      <span>V4 · Bipartite Detail</span>
      <span class="tiny muted">{{ pairsToShow.length }} pair(s) · click hex / lasso in V3</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v4')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body no-pad" ref="wrapRef">
      <svg ref="svgRef" class="bp-svg"></svg>
      <div v-if="!pairsToShow.length" class="overlay muted">no selection — click a hex or use lasso in V3</div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, watch, onMounted, onUnmounted } from 'vue'
import * as d3 from 'd3'
import bus from '../utils/eventbus.js'

const appState = inject('appState')
const svgRef = ref(null)
const wrapRef = ref(null)
const selectedPairs = ref([])

const pairsToShow = computed(() => selectedPairs.value || [])

function onHexSelect(payload) {
  selectedPairs.value = payload?.pairs || []
  draw()
}
function onHexClear() {
  selectedPairs.value = []
  draw()
}

function draw() {
  if (!svgRef.value || !wrapRef.value) return
  const r = wrapRef.value.getBoundingClientRect()
  const W = r.width, H = r.height
  if (!W || !H) return
  const svg = d3.select(svgRef.value).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()
  const pairs = pairsToShow.value
  if (!pairs.length) return
  // Two columns of nodes — husbands on the left, wives on the right.
  const husbands = Array.from(new Set(pairs.map(p => p.husband_id)))
  const wives = Array.from(new Set(pairs.map(p => p.wife_id)))
  const pad = { l: 80, r: 80, t: 24, b: 16 }
  const yH = d3.scalePoint().domain(husbands).range([pad.t, H - pad.b]).padding(0.4)
  const yW = d3.scalePoint().domain(wives).range([pad.t, H - pad.b]).padding(0.4)
  const xH = pad.l, xW = W - pad.r

  // Edges
  svg.append('g').selectAll('path').data(pairs).enter().append('path')
    .attr('d', d => {
      const a = [xH, yH(d.husband_id)], b = [xW, yW(d.wife_id)]
      const mx = (a[0] + b[0]) / 2
      return `M${a[0]},${a[1]} C${mx},${a[1]} ${mx},${b[1]} ${b[0]},${b[1]}`
    })
    .attr('fill', 'none')
    .attr('stroke', d =>
      d.hungarian_correct === true ? '#0f6e56'
      : d.hungarian_correct === false ? '#993c1d'
      : '#888780')
    .attr('stroke-opacity', 0.6)
    .attr('stroke-width', d => 0.6 + 1.6 * Math.min(1, Math.max(0, d.score / 6)))

  // Husband nodes
  svg.append('g').selectAll('g.h').data(husbands).enter().append('g').attr('class', 'h')
    .each(function (id) {
      const g = d3.select(this)
      g.attr('transform', `translate(${xH},${yH(id)})`)
      g.append('circle').attr('r', 5).attr('fill', '#1d9e75').attr('stroke', '#1a1a1a').attr('stroke-width', 0.6)
      g.append('text').attr('x', -10).attr('y', 4).attr('text-anchor', 'end')
        .style('font-size', '10px').text(id)
    })

  // Wife nodes
  svg.append('g').selectAll('g.w').data(wives).enter().append('g').attr('class', 'w')
    .each(function (id) {
      const g = d3.select(this)
      g.attr('transform', `translate(${xW},${yW(id)})`)
      g.append('circle').attr('r', 5).attr('fill', '#ba7517').attr('stroke', '#1a1a1a').attr('stroke-width', 0.6)
      g.append('text').attr('x', 10).attr('y', 4).attr('text-anchor', 'start')
        .style('font-size', '10px').text(id)
    })

  // Title
  svg.append('text').attr('x', W / 2).attr('y', 14).attr('text-anchor', 'middle')
    .style('font-size', '10px').style('fill', '#666')
    .text(`${husbands.length} husbands × ${wives.length} wives · ${pairs.length} pair edges`)
}

watch(() => `${appState.year}|${appState.ablation}`, () => {
  selectedPairs.value = []
  draw()
})

onMounted(() => {
  bus.on('hex-select', onHexSelect)
  bus.on('hex-clear', onHexClear)
  window.addEventListener('resize', draw)
  draw()
})
onUnmounted(() => {
  bus.off('hex-select', onHexSelect)
  bus.off('hex-clear', onHexClear)
  window.removeEventListener('resize', draw)
})
</script>

<style lang="less" scoped>
.bp-svg { width: 100%; height: 100%; display: block; }
.panel-body { position: relative; }
.overlay { position: absolute; inset: 0; display: grid; place-items: center; font-size: 11px; }
</style>
