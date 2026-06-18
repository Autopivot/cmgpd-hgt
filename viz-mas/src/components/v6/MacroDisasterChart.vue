<template>
  <div class="md-wrap" ref="wrapRef">
    <div class="md-head">
      <span class="chip">Disasters (10y)</span>
      <span v-if="error" class="tiny muted">macro service unavailable</span>
    </div>
    <svg v-if="!error" ref="svgRef" class="md-svg"></svg>
    <div v-else class="md-empty tiny muted">macro service unavailable</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as d3 from 'd3'
import axios from 'axios'
import bus from '../../utils/eventbus.js'

const props = defineProps({
  year: { type: Number, required: true },
})

const http = axios.create({ baseURL: '/api', timeout: 30000 })

const wrapRef = ref(null)
const svgRef = ref(null)
const error = ref(false)
const series = ref({ years: [], disaster_count: [] })

async function load() {
  if (!props.year) return
  error.value = false
  try {
    const r = await http.get(`/macro/${props.year}`, { params: { window: 10 } })
    const d = r.data || {}
    series.value = {
      years: Array.isArray(d.years) ? d.years : [],
      disaster_count: Array.isArray(d.disaster_count) ? d.disaster_count : [],
    }
    await nextTick()
    draw()
  } catch (e) {
    error.value = true
    series.value = { years: [], disaster_count: [] }
  }
}

function draw() {
  if (!svgRef.value || !wrapRef.value) return
  const r = wrapRef.value.getBoundingClientRect()
  const W = Math.max(120, r.width)
  const H = Math.max(120, r.height - 22)
  const svg = d3.select(svgRef.value)
    .attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()

  const years = series.value.years || []
  const counts = (series.value.disaster_count || []).map(v => Math.max(0, Math.round(v || 0)))
  const pad = { l: 28, r: 8, t: 8, b: 22 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b

  const root = svg.append('g').attr('transform', `translate(${pad.l},${pad.t})`)

  const allZero = counts.every(v => v === 0)
  if (years.length === 0 || allZero) {
    root.append('text')
      .attr('x', innerW / 2).attr('y', innerH / 2)
      .attr('text-anchor', 'middle')
      .style('font-size', '10px').style('fill', '#999')
      .text(years.length === 0 ? 'no data' : 'no disasters in window')
    if (years.length > 0) {
      const xEmpty = d3.scaleBand().domain(years.map(String)).range([0, innerW]).padding(0.3)
      root.append('g').attr('transform', `translate(0,${innerH})`)
        .call(d3.axisBottom(xEmpty).tickFormat(d => String(d).slice(-2)))
        .selectAll('text').style('font-size', '8px')
    }
    return
  }

  const x = d3.scaleBand()
    .domain(years.map(String))
    .range([0, innerW])
    .padding(0.3)  // 70% width per slot

  const yMax = Math.max(1, d3.max(counts) || 0)
  const y = d3.scaleLinear().domain([0, yMax]).range([innerH, 0])

  // Axes
  root.append('g').attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(x).tickFormat(d => String(d).slice(-2)))
    .selectAll('text').style('font-size', '8px')

  const yTicks = Math.min(4, yMax)
  root.append('g')
    .call(d3.axisLeft(y).ticks(yTicks).tickFormat(d3.format('d')))
    .selectAll('text').style('font-size', '8px')

  // Bars
  root.selectAll('rect.bar').data(years).enter().append('rect')
    .attr('class', 'bar')
    .attr('x', (yr) => x(String(yr)))
    .attr('y', (yr, i) => y(counts[i]))
    .attr('width', x.bandwidth())
    .attr('height', (yr, i) => Math.max(0, innerH - y(counts[i])))
    .attr('fill', '#993c1d')
    .append('title')
    .text((yr, i) => `${yr}: ${counts[i]} disasters`)
}

function onPanelResized({ ids } = {}) {
  if (Array.isArray(ids) && !ids.includes('v6')) return
  draw()
}
function resizeHandler() { draw() }

watch(() => props.year, () => { load() })

onMounted(() => {
  load()
  window.addEventListener('resize', resizeHandler)
  bus.on('panel-resized', onPanelResized)
})
onUnmounted(() => {
  window.removeEventListener('resize', resizeHandler)
  bus.off('panel-resized', onPanelResized)
})
</script>

<style lang="less" scoped>
.md-wrap {
  width: 100%;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.md-head {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 18px;
}
.chip {
  font-size: 10px;
  background: #f3e6df;
  color: #993c1d;
  border: 1px solid #e0c5b8;
  border-radius: 3px;
  padding: 1px 6px;
  font-weight: 600;
}
.tiny { font-size: 9px; }
.muted { color: #888; }
.md-svg {
  width: 100%;
  flex: 1 1 auto;
  min-height: 100px;
}
.md-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1 1 auto;
  min-height: 100px;
}
</style>
