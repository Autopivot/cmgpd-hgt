<template>
  <div class="macro-combined" ref="wrapRef">
    <svg ref="svgRef" class="combined-svg"></svg>
    <div v-if="errored" class="empty tiny muted">macro service unavailable</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import axios from 'axios'
import * as d3 from 'd3'
import bus from '../../utils/eventbus.js'

const http = axios.create({ baseURL: '/api', timeout: 60000 })
const props = defineProps({ year: { type: Number, default: null } })

const wrapRef = ref(null)
const svgRef = ref(null)
const series = ref([])  // [{year, price, low, high, disasters}]
const errored = ref(false)

async function load() {
  if (!props.year) return
  errored.value = false
  try {
    const r = await http.get(`/macro/${encodeURIComponent(props.year)}`, { params: { window: 10 } })
    const d = r.data || {}
    const ys = Array.isArray(d.years) ? d.years : []
    const px = Array.isArray(d.grain_price) ? d.grain_price : []
    const lo = Array.isArray(d.grain_low) ? d.grain_low : px
    const hi = Array.isArray(d.grain_high) ? d.grain_high : px
    const ds = Array.isArray(d.disaster_count) ? d.disaster_count : []
    series.value = ys.map((y, i) => ({
      year: +y, price: +px[i], low: +lo[i], high: +hi[i], disasters: +(ds[i] ?? 0),
    })).filter(d => Number.isFinite(d.year) && Number.isFinite(d.price))
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
  const W = Math.max(160, r.width)
  const H = Math.max(120, r.height)
  const svg = d3.select(svgRef.value)
    .attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()

  const pad = { l: 36, r: 32, t: 18, b: 22 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const root = svg.append('g').attr('transform', `translate(${pad.l},${pad.t})`)

  svg.append('text').attr('x', 6).attr('y', 12)
    .style('font-size', '10px').style('font-weight', 600)
    .style('fill', '#6b5736')
    .text('Grain price + Disasters (10y)')
  svg.append('text').attr('x', W - 6).attr('y', 12)
    .style('font-size', '9px').attr('text-anchor', 'end')
    .style('fill', '#993c1d')
    .text('disasters →')

  const data = series.value
  if (!data.length) {
    root.append('text').attr('x', innerW / 2).attr('y', innerH / 2)
      .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#999')
      .text(errored.value ? 'macro service unavailable' : 'no data')
    return
  }

  const xExtent = d3.extent(data, d => d.year)
  const yPriceMin = d3.min(data, d => d.low ?? d.price)
  const yPriceMax = d3.max(data, d => d.high ?? d.price)
  const pricePad = (yPriceMax - yPriceMin) * 0.1 || 1
  const yDisMax = Math.max(1, d3.max(data, d => d.disasters))

  const xBand = d3.scaleBand().domain(data.map(d => d.year))
    .range([0, innerW]).padding(0.3)
  const xLine = d3.scaleLinear().domain(xExtent).range([
    xBand(data[0].year) + xBand.bandwidth() / 2,
    xBand(data[data.length - 1].year) + xBand.bandwidth() / 2,
  ])
  const yPrice = d3.scaleLinear()
    .domain([yPriceMin - pricePad, yPriceMax + pricePad]).range([innerH, 0])
  const yDis = d3.scaleLinear().domain([0, yDisMax]).nice().range([innerH, 0])

  // Disaster bars (right axis) — drawn first, behind line.
  root.selectAll('rect.bar').data(data).enter().append('rect')
    .attr('class', 'bar')
    .attr('x', d => xBand(d.year))
    .attr('y', d => yDis(d.disasters))
    .attr('width', xBand.bandwidth())
    .attr('height', d => Math.max(0, innerH - yDis(d.disasters)))
    .attr('fill', '#993c1d')
    .attr('fill-opacity', 0.45)
    .append('title').text(d => `${d.year}: ${d.disasters} disasters`)

  // Price LOW–HIGH band (left axis).
  const band = d3.area()
    .x(d => xLine(d.year))
    .y0(d => yPrice(d.low ?? d.price))
    .y1(d => yPrice(d.high ?? d.price))
    .curve(d3.curveMonotoneX)
  root.append('path').datum(data).attr('d', band)
    .attr('fill', '#d4a85d').attr('fill-opacity', 0.18).attr('stroke', 'none')

  // Price line.
  const line = d3.line()
    .x(d => xLine(d.year)).y(d => yPrice(d.price))
    .curve(d3.curveMonotoneX)
  root.append('path').datum(data).attr('d', line)
    .attr('fill', 'none').attr('stroke', '#d4a85d').attr('stroke-width', 1.6)
  root.selectAll('circle').data(data).enter().append('circle')
    .attr('cx', d => xLine(d.year)).attr('cy', d => yPrice(d.price))
    .attr('r', 2.4).attr('fill', '#d4a85d')
    .append('title').text(d => `${d.year}: ${d.price.toFixed(2)} (${d.low.toFixed(2)}–${d.high.toFixed(2)})`)

  // Axes.
  const compactYear = yr => `'${String(yr).slice(-2)}`
  root.append('g').attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(xBand).tickFormat(d => compactYear(d)))
    .selectAll('text').style('font-size', '9px')
  root.append('g').call(d3.axisLeft(yPrice).ticks(4).tickFormat(d3.format('.2~f')))
    .selectAll('text').style('font-size', '9px').style('fill', '#6b5736')
  root.append('g').attr('transform', `translate(${innerW},0)`)
    .call(d3.axisRight(yDis).ticks(Math.min(yDisMax, 4)).tickFormat(d3.format('d')))
    .selectAll('text').style('font-size', '9px').style('fill', '#993c1d')
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

<style scoped lang="less">
.macro-combined {
  position: relative;
  width: 100%; height: 100%; min-height: 0;
  display: flex; flex-direction: column;
}
.combined-svg { width: 100%; flex: 1 1 auto; min-height: 0; }
.empty { position: absolute; bottom: 4px; left: 8px; color: #999; }
</style>
