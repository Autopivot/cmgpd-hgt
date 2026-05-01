<template>
  <div class="income-life" ref="wrapRef">
    <svg ref="svgRef" class="ilc-svg"></svg>
    <div v-if="!hasData" class="empty tiny muted">no income records on register</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, computed, nextTick } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  income: { type: Array, default: () => [] },         // [{year, income, level?}]
  birthYear: { type: Number, default: null },
  cohortYear: { type: Number, required: true },
  height: { type: Number, default: 160 },
})

const wrapRef = ref(null)
const svgRef = ref(null)

const cleaned = computed(() => (props.income || [])
  .map(d => ({ year: +d.year, income: +d.income, level: d.level || null }))
  .filter(d => Number.isFinite(d.year) && Number.isFinite(d.income))
  .sort((a, b) => a.year - b.year))
const hasData = computed(() => cleaned.value.length > 0)

function draw() {
  if (!svgRef.value || !wrapRef.value) return
  const r = wrapRef.value.getBoundingClientRect()
  const W = Math.max(160, r.width)
  const H = Math.max(120, props.height)
  const svg = d3.select(svgRef.value)
    .attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()

  const data = cleaned.value
  const pad = { l: 36, r: 14, t: 14, b: 22 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const root = svg.append('g').attr('transform', `translate(${pad.l},${pad.t})`)

  // x range covers data + cohort + birth so the dashed lines never sit
  // off-canvas.
  const xs = data.map(d => d.year)
  if (Number.isFinite(props.cohortYear)) xs.push(props.cohortYear)
  if (Number.isFinite(props.birthYear)) xs.push(props.birthYear)
  const xMin = Math.min(...xs, props.cohortYear)
  const xMax = Math.max(...xs, props.cohortYear)
  const x = d3.scaleLinear().domain([xMin - 1, xMax + 1]).range([0, innerW])
  const yMax = d3.max(data, d => d.income) || 1
  const y = d3.scaleLinear().domain([0, yMax * 1.05]).range([innerH, 0])

  // axes
  root.append('g').attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(x).ticks(Math.min(8, Math.max(2, xMax - xMin)))
      .tickFormat(d3.format('d')))
    .selectAll('text').style('font-size', '9px')
  root.append('g')
    .call(d3.axisLeft(y).ticks(4).tickFormat(d3.format('.2~f')))
    .selectAll('text').style('font-size', '9px')

  // axis labels
  root.append('text')
    .attr('x', innerW / 2).attr('y', innerH + 18)
    .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#666')
    .text('year')
  root.append('text')
    .attr('transform', `translate(-26,${innerH / 2}) rotate(-90)`)
    .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#666')
    .text('income')

  // birth tick (light, no label)
  if (Number.isFinite(props.birthYear)) {
    root.append('line')
      .attr('x1', x(props.birthYear)).attr('x2', x(props.birthYear))
      .attr('y1', innerH - 4).attr('y2', innerH + 4)
      .attr('stroke', '#888').attr('stroke-width', 1)
    root.append('text')
      .attr('x', x(props.birthYear)).attr('y', innerH - 6)
      .attr('text-anchor', 'middle').style('font-size', '9px').style('fill', '#888')
      .text(`b·${props.birthYear}`)
  }

  // cohort-year vertical dashed line
  if (Number.isFinite(props.cohortYear)) {
    root.append('line')
      .attr('class', 'cohort-marker')
      .attr('x1', x(props.cohortYear)).attr('x2', x(props.cohortYear))
      .attr('y1', 0).attr('y2', innerH)
      .attr('stroke', '#993c1d').attr('stroke-width', 1.2)
      .attr('stroke-dasharray', '4 3')
    root.append('text')
      .attr('x', x(props.cohortYear) + 4).attr('y', 12)
      .style('font-size', '9px').style('fill', '#993c1d')
      .text(`cohort ${props.cohortYear}`)
  }

  if (!data.length) return

  // faint area + line
  const area = d3.area()
    .x(d => x(d.year)).y0(innerH).y1(d => y(d.income))
    .curve(d3.curveMonotoneX)
  root.append('path').datum(data).attr('d', area)
    .attr('fill', '#d4a85d').attr('fill-opacity', 0.15)
  const line = d3.line()
    .x(d => x(d.year)).y(d => y(d.income))
    .curve(d3.curveMonotoneX)
  root.append('path').datum(data).attr('d', line)
    .attr('fill', 'none').attr('stroke', '#d4a85d').attr('stroke-width', 1.6)
  root.selectAll('circle').data(data).enter().append('circle')
    .attr('cx', d => x(d.year)).attr('cy', d => y(d.income))
    .attr('r', 2.4).attr('fill', '#d4a85d')
    .append('title').text(d =>
      `${d.year}: ${d3.format('.3~f')(d.income)}${d.level ? ' (' + d.level + ')' : ''}`,
    )
}

watch(() => [props.income, props.cohortYear, props.birthYear, props.height],
  async () => { await nextTick(); draw() }, { deep: true })

const onResize = () => draw()
onMounted(async () => {
  await nextTick()
  draw()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<style scoped lang="less">
.income-life {
  position: relative;
  width: 100%;
  min-height: 120px;
}
.ilc-svg { width: 100%; display: block; }
.empty {
  position: absolute; inset: 0;
  display: grid; place-items: center;
  color: #888; font-style: italic;
}
</style>
