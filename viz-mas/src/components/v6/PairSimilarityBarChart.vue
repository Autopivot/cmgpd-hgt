<template>
  <div class="pair-sim-root">
    <div v-if="!husband || !husband.husband_id" class="empty-state">
      select a husband in V4 to see candidate similarity
    </div>
    <template v-else>
      <div class="tabs">
        <button
          v-for="m in METRICS"
          :key="m.key"
          class="tab-btn"
          :class="{ on: metric === m.key }"
          @click="metric = m.key"
        >{{ m.label }}</button>
      </div>
      <div class="chart-host" ref="hostRef">
        <svg ref="svgRef" class="bar-svg"></svg>
        <div v-if="loading" class="hint">loading…</div>
        <div v-else-if="!candidates || candidates.length === 0" class="hint">
          no candidates
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as d3 from 'd3'
import axios from 'axios'
import bus from '../../utils/eventbus.js'

const props = defineProps({
  husband: { type: Object, default: null },
  candidates: { type: Array, default: () => [] },
})

const METRICS = [
  { key: 'paternal_lineage_proximity', label: 'paternal lineage proximity' },
  { key: 'shared_siblings',            label: 'shared siblings' },
  { key: 'same_household_history',     label: 'same household history' },
  { key: 'same_banner',                label: 'same banner' },
]

const metric = ref('paternal_lineage_proximity')
const loading = ref(false)
const hostRef = ref(null)
const svgRef = ref(null)

// Cache: `${husband_id}|${wife_id}` → features object | { _err: true }
const cache = new Map()
// Reactive bag of fetched feature rows for the current husband.
const features = ref(new Map())

const http = axios.create({ baseURL: '/api', timeout: 30000 })

async function fetchPair(hid, wid) {
  const k = `${hid}|${wid}`
  if (cache.has(k)) return cache.get(k)
  try {
    const r = await http.get(`/pair-features/${encodeURIComponent(hid)}/${encodeURIComponent(wid)}`)
    cache.set(k, r.data)
    return r.data
  } catch (e) {
    const stub = { _err: true }
    cache.set(k, stub)
    return stub
  }
}

async function fetchAll() {
  const h = props.husband
  if (!h || h.husband_id == null) return
  const cands = props.candidates || []
  loading.value = true
  const hid = h.husband_id
  const results = await Promise.all(cands.map(c => fetchPair(hid, c.wife_id)))
  const next = new Map()
  cands.forEach((c, i) => { next.set(c.wife_id, results[i]) })
  features.value = next
  loading.value = false
  await nextTick()
  draw()
}

function valueFor(wifeId) {
  const f = features.value.get(wifeId)
  if (!f || f._err) return { value: 0, missing: true }
  let v = 0
  switch (metric.value) {
    case 'paternal_lineage_proximity':
      v = Number(f.paternal_lineage_proximity ?? f.paternal_proximity ?? 0); break
    case 'shared_siblings':
      v = Number(f.shared_siblings ?? 0); break
    case 'same_household_history':
      v = Number(f.same_household_history ?? f.household_share ?? 0); break
    case 'same_banner':
      v = f.same_banner ? 1 : 0; break
  }
  if (!Number.isFinite(v)) v = 0
  return { value: v, missing: false }
}

function draw() {
  const host = hostRef.value
  const svgEl = svgRef.value
  if (!host || !svgEl) return
  const w = Math.max(120, host.clientWidth)
  const h = Math.max(180, host.clientHeight)
  const svg = d3.select(svgEl)
  svg.selectAll('*').remove()
  svg.attr('width', w).attr('height', h)

  const cands = props.candidates || []
  if (!cands.length) return

  const rows = cands.map(c => {
    const v = valueFor(c.wife_id)
    return { wife_id: c.wife_id, value: v.value, missing: v.missing }
  })
  rows.sort((a, b) => d3.descending(a.value, b.value))

  const margin = { top: 6, right: 28, bottom: 18, left: 78 }
  const innerW = Math.max(20, w - margin.left - margin.right)
  const innerH = Math.max(20, h - margin.top - margin.bottom)
  const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

  const maxV = d3.max(rows, d => d.value) || 1
  const x = d3.scaleLinear().domain([0, Math.max(1e-9, maxV)]).range([0, innerW])
  const y = d3.scaleBand()
    .domain(rows.map(r => String(r.wife_id)))
    .range([0, innerH])
    .padding(0.18)

  // Axes
  g.append('g')
    .attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(x).ticks(4).tickFormat(d3.format('.2~f')))
    .call(s => s.selectAll('text').attr('font-size', 9).attr('fill', '#444'))
    .call(s => s.selectAll('path,line').attr('stroke', '#bbb'))
  g.append('g')
    .call(d3.axisLeft(y))
    .call(s => s.selectAll('text').attr('font-size', 10).attr('fill', '#222'))
    .call(s => s.selectAll('path,line').attr('stroke', '#bbb'))

  // Tooltip
  let tip = d3.select(host).select('.bar-tip')
  if (tip.empty()) {
    tip = d3.select(host).append('div').attr('class', 'bar-tip')
  }
  tip.style('opacity', 0)

  g.selectAll('rect.candidate-bar')
    .data(rows, d => d.wife_id)
    .enter()
    .append('rect')
    .attr('class', 'candidate-bar')
    .attr('x', 0)
    .attr('y', d => y(String(d.wife_id)))
    .attr('height', y.bandwidth())
    .attr('width', d => Math.max(0.5, x(d.value)))
    .attr('fill', '#0f6e56')
    .attr('opacity', d => d.missing ? 0.35 : 1)
    .on('mousemove', (event, d) => {
      const [mx, my] = d3.pointer(event, host)
      tip.style('left', `${mx + 10}px`)
        .style('top', `${my + 8}px`)
        .style('opacity', 1)
        .html(d.missing
          ? `wife_id=${d.wife_id}<br>?`
          : `wife_id=${d.wife_id}<br>${d3.format('.4~f')(d.value)}`)
    })
    .on('mouseleave', () => { tip.style('opacity', 0) })

  // Missing-value "?" labels
  g.selectAll('text.miss-label')
    .data(rows.filter(r => r.missing))
    .enter()
    .append('text')
    .attr('class', 'miss-label')
    .attr('x', 4)
    .attr('y', d => y(String(d.wife_id)) + y.bandwidth() / 2)
    .attr('dy', '0.35em')
    .attr('font-size', 10)
    .attr('fill', '#a33')
    .text('?')

  // Value labels at bar end
  g.selectAll('text.val-label')
    .data(rows.filter(r => !r.missing))
    .enter()
    .append('text')
    .attr('class', 'val-label')
    .attr('x', d => x(d.value) + 3)
    .attr('y', d => y(String(d.wife_id)) + y.bandwidth() / 2)
    .attr('dy', '0.35em')
    .attr('font-size', 9)
    .attr('fill', '#333')
    .text(d => d3.format('.2~f')(d.value))
}

function onPanelResized({ ids } = {}) {
  if (Array.isArray(ids) && !ids.includes('v6')) return
  draw()
}
function resizeHandler() { draw() }

// Re-fetch only when husband_id changes (or candidates list changes).
watch(
  () => [props.husband?.husband_id, (props.candidates || []).map(c => c.wife_id).join(',')],
  () => { fetchAll() },
  { immediate: false },
)

// Re-render (no fetch) when metric changes.
watch(metric, () => { draw() })

onMounted(() => {
  bus.on('panel-resized', onPanelResized)
  window.addEventListener('resize', resizeHandler)
  if (props.husband?.husband_id) fetchAll()
})
onUnmounted(() => {
  bus.off('panel-resized', onPanelResized)
  window.removeEventListener('resize', resizeHandler)
})
</script>

<style scoped lang="less">
.pair-sim-root {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}
.empty-state {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #888;
  font-size: 11px;
  font-style: italic;
}
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  padding: 2px 0 4px 0;
}
.tab-btn {
  font-size: 10px;
  padding: 2px 6px;
  border: 1px solid #888;
  border-radius: 3px;
  background: #f5f5f5;
  color: #1a1a1a;
  cursor: pointer;
  &:hover { background: #fff3c4; border-color: #d4a85d; }
  &.on {
    background: #ffe082;
    border-color: #d4a85d;
    font-weight: 700;
  }
}
.chart-host {
  position: relative;
  flex: 1 1 auto;
  width: 100%;
  min-height: 180px;
}
.bar-svg {
  width: 100%;
  height: 100%;
  display: block;
}
.hint {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  color: #888;
  font-size: 11px;
  font-style: italic;
}
:deep(.bar-tip) {
  position: absolute;
  pointer-events: none;
  background: rgba(20, 20, 20, 0.92);
  color: #fff;
  font-size: 10px;
  padding: 3px 6px;
  border-radius: 3px;
  opacity: 0;
  transition: opacity 80ms;
  white-space: nowrap;
  z-index: 10;
}
</style>
