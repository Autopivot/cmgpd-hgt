<template>
  <div class="panel">
    <div class="panel-head">
      <span>V1 · Overview · Completion Metrics</span>
      <span class="tiny muted">{{ ablation }} · {{ ALL_YEARS.length }} cohorts</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v1')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body" ref="wrapRef">
      <svg ref="svgRef" class="lines-svg"></svg>
      <table class="dense" style="margin-top: 8px;">
        <thead>
          <tr><th>year</th><th class="num">n_pos</th><th class="num">recall@1</th><th class="num">top1</th><th class="num">top10</th><th class="num">MRR</th></tr>
        </thead>
        <tbody>
          <tr v-for="m in metrics" :key="m.year"
              :class="{ active: m.year === appState.year }"
              @click="setYear(m.year)">
            <td>{{ m.year }}</td>
            <td class="num">{{ m.n_positives ?? '—' }}</td>
            <td class="num">{{ fmt(m.hungarian_recall_at_1) }}</td>
            <td class="num">{{ fmt(m.top1_recall) }}</td>
            <td class="num">{{ fmt(m.top10_recall) }}</td>
            <td class="num">{{ fmt(m.mrr) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as d3 from 'd3'
import { getMetrics, ALL_YEARS } from '../api/client.js'
import bus from '../utils/eventbus.js'

const appState = inject('appState')
const ablation = computed(() => appState.ablation)
const metrics = ref([])
const svgRef = ref(null)
const wrapRef = ref(null)

function fmt(v) { return Number.isFinite(v) ? v.toFixed(3) : '—' }

function setYear(y) {
  appState.year = y
  bus.emit('cohort-changed', { year: y, ablation: appState.ablation })
}

async function load() {
  metrics.value = await getMetrics({ ablation: appState.ablation })
  await nextTick()
  draw()
}

function draw() {
  if (!svgRef.value || !wrapRef.value) return
  const r = wrapRef.value.getBoundingClientRect()
  const W = r.width, H = Math.min(120, r.height * 0.45)
  const svg = d3.select(svgRef.value)
    .attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()
  const m = metrics.value.filter(d => Number.isFinite(d.hungarian_recall_at_1))
  if (!m.length) return
  const pad = { l: 30, r: 14, t: 8, b: 18 }
  const x = d3.scalePoint().domain(m.map(d => d.year)).range([pad.l, W - pad.r])
  const y = d3.scaleLinear().domain([0, 1]).range([H - pad.b, pad.t])
  // Axes
  svg.append('g').attr('transform', `translate(0,${H - pad.b})`)
    .call(d3.axisBottom(x).tickFormat(d => d).tickSizeOuter(0))
    .selectAll('text').style('font-size', '9px')
  svg.append('g').attr('transform', `translate(${pad.l},0)`)
    .call(d3.axisLeft(y).ticks(4).tickFormat(d => d.toFixed(1)))
    .selectAll('text').style('font-size', '9px')
  // Three series
  const series = [
    { key: 'hungarian_recall_at_1', color: '#0f6e56', label: 'recall@1' },
    { key: 'top10_recall',          color: '#ba7517', label: 'top10' },
    { key: 'mrr',                   color: '#7f77dd', label: 'MRR' },
  ]
  for (const s of series) {
    const line = d3.line().x(d => x(d.year)).y(d => y(d[s.key]))
    svg.append('path').datum(m)
      .attr('d', line)
      .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', 1.5)
    svg.selectAll(`.dot-${s.key}`).data(m).enter().append('circle')
      .attr('cx', d => x(d.year)).attr('cy', d => y(d[s.key])).attr('r', 2.5)
      .attr('fill', s.color)
  }
  // Legend
  const legend = svg.append('g').attr('transform', `translate(${pad.l + 6},${pad.t + 2})`)
    .selectAll('g').data(series).enter().append('g')
    .attr('transform', (_, i) => `translate(${i * 56},0)`)
  legend.append('rect').attr('width', 8).attr('height', 8).attr('fill', d => d.color)
  legend.append('text').attr('x', 11).attr('y', 8).style('font-size', '9px').text(d => d.label)
}

watch(() => appState.ablation, load)
onMounted(() => {
  load()
  window.addEventListener('resize', draw)
})
onUnmounted(() => window.removeEventListener('resize', draw))
</script>

<style lang="less" scoped>
.panel-body { display: flex; flex-direction: column; }
.lines-svg { width: 100%; flex: 0 0 auto; }
table.dense .num { text-align: right; font-variant-numeric: tabular-nums; }
</style>
