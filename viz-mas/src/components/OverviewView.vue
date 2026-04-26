<template>
  <div class="panel">
    <div class="panel-head">
      <span>V1 · Overview · MAS Acceptance Curve</span>
      <span class="tiny muted">{{ statusLine }}</span>
      <button class="btn ghost tiny" :title="resetTitle" @click="reset">↺ reset</button>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v1')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body" ref="wrapRef">
      <svg ref="svgRef" class="curve-svg"></svg>
      <div class="legend tiny">
        <span class="sw mas"></span>MAS recall@1 vs accepted relations
        <span class="sw hgt"></span>HGT static baseline ({{ baselineLabel }})
      </div>
      <div class="footnote tiny muted">
        x-axis = cumulative # of relations accepted in this cohort (V5 ▶ arena
        accepts, manual overrides, auto-commits). y-axis = running fraction
        of accepted matches that hit the cohort's ground-truth wife. The
        dashed horizontal is HGT-only Hungarian recall@1 — the baseline
        you have to beat with the agent loop.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as d3 from 'd3'
import { getEvalProgress, resetEvalLog } from '../api/client.js'
import bus from '../utils/eventbus.js'

const appState = inject('appState')
const svgRef = ref(null)
const wrapRef = ref(null)
const data = ref({
  hgt_baseline: { recall_at_1: 0, n_positives: 0 },
  trajectory: [],
  n_accepted_total: 0,
  n_eligible_total: 0,
  n_correct_total: 0,
  mas_recall_at_1_now: null,
})

const baselineLabel = computed(() => data.value.hgt_baseline?.recall_at_1?.toFixed(3) ?? '—')
const statusLine = computed(() => {
  const d = data.value
  const now = d.mas_recall_at_1_now
  return `${appState.ablation} · ${d.n_accepted_total} accepted · `
       + `${d.n_correct_total}/${d.n_eligible_total} correct`
       + (now != null ? ` · MAS=${now.toFixed(3)}` : '')
})
const resetTitle = computed(() => 'Clear the accept log + per-husband latest map (server-side)')

async function load() {
  data.value = await getEvalProgress({ year: appState.year, ablation: appState.ablation })
  await nextTick()
  draw()
}

async function reset() {
  await resetEvalLog()
  await load()
}

function draw() {
  if (!svgRef.value || !wrapRef.value) return
  const r = wrapRef.value.getBoundingClientRect()
  const W = r.width, H = Math.max(140, r.height - 60)
  const svg = d3.select(svgRef.value)
    .attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()

  const traj = data.value.trajectory || []
  const baseline = data.value.hgt_baseline?.recall_at_1 ?? 0
  const pad = { l: 38, r: 12, t: 14, b: 26 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b

  // x = cumulative # accepted; y = running MAS recall@1 (in [0,1])
  const xMax = Math.max(8, traj.length)
  const x = d3.scaleLinear().domain([0, xMax]).range([0, innerW])
  const y = d3.scaleLinear().domain([0, 1]).range([innerH, 0])

  const root = svg.append('g').attr('transform', `translate(${pad.l},${pad.t})`)

  // Axes
  root.append('g').attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(x).ticks(Math.min(8, xMax)).tickFormat(d3.format('d')))
    .selectAll('text').style('font-size', '9px')
  root.append('g')
    .call(d3.axisLeft(y).ticks(5).tickFormat(d => d.toFixed(1)))
    .selectAll('text').style('font-size', '9px')

  // Axis labels
  root.append('text')
    .attr('x', innerW / 2).attr('y', innerH + 22)
    .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#666')
    .text('# relations accepted')
  root.append('text')
    .attr('transform', `translate(-28,${innerH / 2}) rotate(-90)`)
    .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#666')
    .text('recall@1')

  // HGT static baseline — dashed horizontal
  root.append('line')
    .attr('x1', 0).attr('x2', innerW)
    .attr('y1', y(baseline)).attr('y2', y(baseline))
    .attr('stroke', '#1d9e75').attr('stroke-width', 1.4)
    .attr('stroke-dasharray', '5 4')
  root.append('text')
    .attr('x', innerW - 4).attr('y', Math.max(10, y(baseline) - 4))
    .attr('text-anchor', 'end').style('font-size', '9px').style('fill', '#1d9e75')
    .text(`HGT ${baseline.toFixed(3)}`)

  // MAS trajectory (only points where mas_recall_at_1 is non-null)
  const eligible = traj.filter(p => p.mas_recall_at_1 != null)
  if (eligible.length > 0) {
    const line = d3.line()
      .x(p => x(p.n_accepted))
      .y(p => y(p.mas_recall_at_1))
      .curve(d3.curveStepAfter)
    root.append('path').datum(eligible)
      .attr('d', line)
      .attr('fill', 'none').attr('stroke', '#993c1d').attr('stroke-width', 1.6)
    root.selectAll('circle').data(eligible).enter().append('circle')
      .attr('cx', p => x(p.n_accepted)).attr('cy', p => y(p.mas_recall_at_1))
      .attr('r', 2.8).attr('fill', '#993c1d')
      .append('title').text(p =>
        `accepted=${p.n_accepted}, correct=${p.n_correct}/${p.n_eligible} `
        + `(${p.husband_id} → ${p.wife_id} · ${p.source})`,
      )
  } else {
    // Empty-state hint
    root.append('text')
      .attr('x', innerW / 2).attr('y', innerH / 2)
      .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#999')
      .text('no acceptances yet — open V5 and click ▶ arena, then accept a candidate')
  }
}

// Re-load when the cohort changes or any match is accepted upstream.
watch(() => `${appState.year}|${appState.ablation}`, load)
function onMatchAccepted() { load() }

onMounted(() => {
  load()
  bus.on('match-accepted', onMatchAccepted)
  window.addEventListener('resize', draw)
})
onUnmounted(() => {
  bus.off('match-accepted', onMatchAccepted)
  window.removeEventListener('resize', draw)
})
</script>

<style lang="less" scoped>
.panel-body { display: flex; flex-direction: column; gap: 4px; }
.curve-svg { width: 100%; flex: 1 1 auto; min-height: 140px; }
.legend {
  display: flex; align-items: center; gap: 12px;
  font-size: 10px; color: #555;
  .sw {
    display: inline-block; width: 14px; height: 4px; margin-right: 4px;
    vertical-align: middle;
    &.mas { background: #993c1d; }
    &.hgt { background: repeating-linear-gradient(to right, #1d9e75 0 5px, transparent 5px 9px); }
  }
}
.footnote { padding: 0 2px; line-height: 1.35; }
.btn.ghost.tiny { font-size: 9px; padding: 1px 6px; margin-left: 4px; }
</style>
