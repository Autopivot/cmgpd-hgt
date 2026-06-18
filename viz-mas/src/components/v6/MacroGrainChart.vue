<template>
  <div class="macro-grain" ref="wrapRef">
    <svg ref="svgRef" class="grain-svg"></svg>
    <div v-if="errored" class="empty tiny muted">macro service unavailable</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import axios from 'axios'
import * as d3 from 'd3'
import bus from '../../utils/eventbus.js'

// Mirror src/api/client.js axios convention.
const http = axios.create({ baseURL: '/api', timeout: 60000 })

const props = defineProps({ year: { type: Number, default: null } })

const wrapRef = ref(null)
const svgRef = ref(null)
const series = ref([])   // [{year, price, low, high}]
const errored = ref(false)

async function load() {
  if (!props.year) return
  errored.value = false
  try {
    const r = await http.get(`/macro/${encodeURIComponent(props.year)}`, {
      params: { window: 10 },
    })
    const d = r.data || {}
    const ys = Array.isArray(d.years) ? d.years : []
    const px = Array.isArray(d.grain_price) ? d.grain_price : []
    const lo = Array.isArray(d.grain_low) ? d.grain_low : px
    const hi = Array.isArray(d.grain_high) ? d.grain_high : px
    series.value = ys
      .map((y, i) => ({ year: +y, price: +px[i], low: +lo[i], high: +hi[i] }))
      .filter(d => Number.isFinite(d.year) && Number.isFinite(d.price))
  } catch {
    errored.value = true
    series.value = []
  }
  await nextTick()
  draw()
}

function draw() {
  if (!svgRef.value || !wrapRef.value) return
  const r = wrapRef.value.getBoundingClientRect()
  const W = Math.max(120, r.width)
  const H = Math.max(120, r.height)
  const svg = d3.select(svgRef.value)
    .attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()

  const pad = { l: 32, r: 8, t: 18, b: 22 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const root = svg.append('g').attr('transform', `translate(${pad.l},${pad.t})`)

  // Title chip — anchored top-left.
  svg.append('text')
    .attr('x', 6).attr('y', 12)
    .style('font-size', '10px').style('fill', '#6b5736').style('font-weight', 600)
    .text('Grain price (10y)')

  const data = series.value
  if (!data.length) {
    root.append('text')
      .attr('x', innerW / 2).attr('y', innerH / 2)
      .attr('text-anchor', 'middle')
      .style('font-size', '10px').style('fill', '#999')
      .text(errored.value ? 'macro service unavailable' : 'no data')
    return
  }

  const xExtent = d3.extent(data, d => d.year)
  const yMin = d3.min(data, d => d.low ?? d.price)
  const yMax = d3.max(data, d => d.high ?? d.price)
  const yPad = (yMax - yMin) * 0.1 || 1

  const x = d3.scaleLinear().domain(xExtent).range([0, innerW])
  const y = d3.scaleLinear()
    .domain([yMin - yPad, yMax + yPad])
    .range([innerH, 0])

  // LOW–HIGH band — faint gold area showing the spread across grain types.
  const band = d3.area()
    .x(d => x(d.year))
    .y0(d => y(d.low ?? d.price))
    .y1(d => y(d.high ?? d.price))
    .curve(d3.curveMonotoneX)
  root.append('path').datum(data)
    .attr('d', band)
    .attr('fill', '#d4a85d')
    .attr('fill-opacity', 0.18)
    .attr('stroke', 'none')

  // Axes — bottom + left.
  const compactYear = yr => `'${String(yr).slice(-2)}`
  root.append('g').attr('transform', `translate(0,${innerH})`)
    .call(
      d3.axisBottom(x)
        .ticks(Math.min(data.length, 6))
        .tickFormat(d => compactYear(Math.round(d))),
    )
    .selectAll('text').style('font-size', '9px')

  root.append('g')
    .call(d3.axisLeft(y).ticks(4).tickFormat(d => d3.format('.2~f')(d)))
    .selectAll('text').style('font-size', '9px')

  // Line — gold.
  const line = d3.line()
    .x(d => x(d.year))
    .y(d => y(d.price))
    .curve(d3.curveMonotoneX)

  root.append('path').datum(data)
    .attr('d', line)
    .attr('fill', 'none')
    .attr('stroke', '#d4a85d')
    .attr('stroke-width', 1.5)

  // Dots.
  root.selectAll('circle').data(data).enter().append('circle')
    .attr('cx', d => x(d.year))
    .attr('cy', d => y(d.price))
    .attr('r', 2.5)
    .attr('fill', '#d4a85d')
    .append('title').text(d => `${d.year}: ${d.price}`)
}

watch(() => props.year, load)

const onPanelResized = (ids) => {
  if (Array.isArray(ids) ? ids.includes('v6') : ids === 'v6') draw()
}
const onResize = () => draw()

onMounted(() => {
  load()
  bus.on('panel-resized', onPanelResized)
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  bus.off('panel-resized', onPanelResized)
  window.removeEventListener('resize', onResize)
})
</script>

<style lang="less" scoped>
.macro-grain {
  position: relative;
  width: 100%;
  min-height: 120px;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.grain-svg {
  width: 100%;
  flex: 1 1 auto;
  min-height: 120px;
}
.empty {
  position: absolute;
  bottom: 4px;
  left: 8px;
  color: #999;
}
</style>
