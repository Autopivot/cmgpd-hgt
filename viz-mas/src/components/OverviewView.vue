<template>
  <div class="panel">
    <div class="panel-head">
      <span>V1: Overview</span>
      <span class="tiny muted">{{ statusLine }}</span>
      <button class="btn ghost tiny" :title="resetTitle" @click="reset">↺ reset</button>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v1')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body" ref="wrapRef">
      <svg ref="svgRef" class="curve-svg"></svg>
      <div class="legend tiny" v-if="evalMode">
        <span class="sw mas"></span>MAS recall@1 vs accepted relations
        <span class="sw hgt"></span>HGT static baseline ({{ baselineLabel }})
      </div>
      <div class="legend tiny" v-else>
        <span class="sw hist"></span>HGT pair score distribution
        <span class="sw meanline"></span>cohort mean
        <span class="muted">{{ summaryChip }}</span>
      </div>
      <div class="footnote tiny muted" v-if="evalMode">
        x-axis = cumulative # of relations accepted in this cohort (V5 ▶ arena
        accepts, manual overrides, auto-commits). y-axis = running fraction
        of accepted matches that hit the cohort's ground-truth wife. The
        dashed horizontal is HGT-only Hungarian recall@1 — the baseline
        you have to beat with the agent loop.
      </div>
      <div class="footnote tiny muted" v-else>
        no GT in {{ appState.year }} — V1 summarises the HGT score
        distribution of every (husband, wife) pair in the current cohort.
        Higher density at high scores = the model is generally confident on
        this cohort; a fat low-end tail = many uncertain candidates that
        will need MAS deliberation. Vertical line marks the cohort mean;
        ticks at quartiles. Right-margin chips count {{ data.n_accepted_total }}
        accepted edges so far.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as d3 from 'd3'
import { getEvalProgress, resetEvalLog, loadCohort } from '../api/client.js'
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
const totalHusbands = ref(0)
const cohortStats = ref(null)  // { n_pairs, n_husbands, mean, median, p25, p75, p90, min, max, scores: number[] }

const evalMode = computed(() => appState.year === 1882)

const baselineLabel = computed(() => data.value.hgt_baseline?.recall_at_1?.toFixed(3) ?? '—')
const statusLine = computed(() => {
  const d = data.value
  if (evalMode.value) {
    const now = d.mas_recall_at_1_now
    return `${appState.ablation} · ${d.n_accepted_total} accepted · `
         + `${d.n_correct_total}/${d.n_eligible_total} correct`
         + (now != null ? ` · MAS=${now.toFixed(3)}` : '')
  }
  const c = cohortStats.value
  if (!c) return `${appState.ablation} · loading…`
  return `${appState.ablation} · ${c.n_pairs} pairs · ${c.n_husbands} husbands · `
       + `mean=${c.mean.toFixed(2)} · ${d.n_accepted_total} committed`
})
const summaryChip = computed(() => {
  const c = cohortStats.value
  if (!c) return ''
  return `n=${c.n_pairs} · μ=${c.mean.toFixed(2)} · med=${c.median.toFixed(2)} `
       + `· p25=${c.p25.toFixed(2)} · p75=${c.p75.toFixed(2)} · max=${c.max.toFixed(2)}`
})
const resetTitle = computed(() => 'Clear the accept log + per-husband latest map (server-side)')

function _summarise(scores) {
  const n = scores.length
  if (!n) return null
  const sorted = scores.slice().sort((a, b) => a - b)
  const pct = (p) => sorted[Math.max(0, Math.min(n - 1, Math.round((n - 1) * p)))]
  const mean = sorted.reduce((s, v) => s + v, 0) / n
  return {
    n_pairs: n,
    mean,
    median: pct(0.5),
    p25: pct(0.25),
    p75: pct(0.75),
    p90: pct(0.9),
    min: sorted[0],
    max: sorted[n - 1],
  }
}

async function load() {
  const [progress, cohort] = await Promise.all([
    getEvalProgress({ year: appState.year, ablation: appState.ablation }),
    loadCohort(appState.year, appState.ablation).catch(() => null),
  ])
  data.value = progress
  if (cohort?.pairs?.length) {
    totalHusbands.value = new Set(cohort.pairs.map(p => p.husband_id)).size
    if (!evalMode.value) {
      const scores = cohort.pairs.map(p => +p.score).filter(Number.isFinite)
      const stats = _summarise(scores)
      if (stats) {
        cohortStats.value = { ...stats, n_husbands: totalHusbands.value, scores }
      }
    } else {
      cohortStats.value = null
    }
  } else {
    totalHusbands.value = 0
    cohortStats.value = null
  }
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

  const pad = { l: 38, r: 12, t: 14, b: 26 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const root = svg.append('g').attr('transform', `translate(${pad.l},${pad.t})`)

  if (evalMode.value) {
    drawEvalCurve(root, innerW, innerH)
  } else {
    drawHGTHist(root, innerW, innerH)
  }
}

function drawEvalCurve(root, innerW, innerH) {
  const traj = data.value.trajectory || []
  const xMax = Math.max(8, traj.length)
  const x = d3.scaleLinear().domain([0, xMax]).range([0, innerW])
  const y = d3.scaleLinear().domain([0, 1]).range([innerH, 0])

  root.append('g').attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(x).ticks(8).tickFormat(d3.format('d')))
    .selectAll('text').style('font-size', '9px')
  root.append('g')
    .call(d3.axisLeft(y).ticks(5).tickFormat(d => d.toFixed(1)))
    .selectAll('text').style('font-size', '9px')
  root.append('text')
    .attr('x', innerW / 2).attr('y', innerH + 22)
    .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#666')
    .text('# relations accepted')
  root.append('text')
    .attr('transform', `translate(-28,${innerH / 2}) rotate(-90)`)
    .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#666')
    .text('recall@1')

  const baseline = data.value.hgt_baseline?.recall_at_1 ?? 0
  root.append('line')
    .attr('x1', 0).attr('x2', innerW)
    .attr('y1', y(baseline)).attr('y2', y(baseline))
    .attr('stroke', '#1d9e75').attr('stroke-width', 1.4)
    .attr('stroke-dasharray', '5 4')
  root.append('text')
    .attr('x', innerW - 4).attr('y', Math.max(10, y(baseline) - 4))
    .attr('text-anchor', 'end').style('font-size', '9px').style('fill', '#1d9e75')
    .text(`HGT ${baseline.toFixed(3)}`)

  const eligible = traj.filter(p => p.mas_recall_at_1 != null)
  if (eligible.length === 0) {
    root.append('text')
      .attr('x', innerW / 2).attr('y', innerH / 2)
      .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#999')
      .text('no acceptances yet — open V5 and click ▶ arena, then accept a candidate')
    return
  }
  const line = d3.line()
    .x(p => x(p.n_accepted)).y(p => y(p.mas_recall_at_1))
    .curve(d3.curveStepAfter)
  root.append('path').datum(eligible)
    .attr('d', line).attr('fill', 'none')
    .attr('stroke', '#993c1d').attr('stroke-width', 1.6)
  root.selectAll('circle').data(eligible).enter().append('circle')
    .attr('cx', p => x(p.n_accepted)).attr('cy', p => y(p.mas_recall_at_1))
    .attr('r', 2.8).attr('fill', '#993c1d')
    .append('title').text(p =>
      `accepted=${p.n_accepted}, correct=${p.n_correct}/${p.n_eligible} `
      + `(${p.husband_id} → ${p.wife_id} · ${p.source})`,
    )
}

function drawHGTHist(root, innerW, innerH) {
  const c = cohortStats.value
  if (!c) {
    root.append('text')
      .attr('x', innerW / 2).attr('y', innerH / 2)
      .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#999')
      .text('cohort not loaded — check backend')
    return
  }
  const x = d3.scaleLinear()
    .domain([Math.min(c.min, 0), Math.max(c.max, 1)])
    .nice()
    .range([0, innerW])
  const bins = d3.bin().domain(x.domain()).thresholds(36)(c.scores)
  const yMax = d3.max(bins, b => b.length) || 1
  const y = d3.scaleLinear().domain([0, yMax]).range([innerH, 0])

  // x-axis
  root.append('g').attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(x).ticks(8))
    .selectAll('text').style('font-size', '9px')
  root.append('text')
    .attr('x', innerW / 2).attr('y', innerH + 22)
    .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#666')
    .text('HGT pair score (logit)')
  // y-axis
  root.append('g')
    .call(d3.axisLeft(y).ticks(4).tickFormat(d3.format('d')))
    .selectAll('text').style('font-size', '9px')
  root.append('text')
    .attr('transform', `translate(-28,${innerH / 2}) rotate(-90)`)
    .attr('text-anchor', 'middle').style('font-size', '10px').style('fill', '#666')
    .text('# pairs')

  // IQR band (p25..p75)
  root.append('rect')
    .attr('x', x(c.p25)).attr('y', 0)
    .attr('width', Math.max(0, x(c.p75) - x(c.p25)))
    .attr('height', innerH)
    .attr('fill', '#d4a85d').attr('fill-opacity', 0.10)

  // Bars
  root.selectAll('rect.score-bin').data(bins).enter().append('rect')
    .attr('class', 'score-bin')
    .attr('x', b => x(b.x0) + 1)
    .attr('y', b => y(b.length))
    .attr('width', b => Math.max(0, x(b.x1) - x(b.x0) - 1))
    .attr('height', b => innerH - y(b.length))
    .attr('fill', '#5d839a').attr('fill-opacity', 0.78)
    .append('title').text(b => `${b.x0.toFixed(2)} … ${b.x1.toFixed(2)} : ${b.length} pairs`)

  // Mean line
  root.append('line')
    .attr('x1', x(c.mean)).attr('x2', x(c.mean))
    .attr('y1', 0).attr('y2', innerH)
    .attr('stroke', '#993c1d').attr('stroke-width', 1.6)
  root.append('text')
    .attr('x', x(c.mean) + 4).attr('y', 12)
    .style('font-size', '9px').style('fill', '#993c1d')
    .text(`μ=${c.mean.toFixed(2)}`)

  // Median tick on x-axis
  root.append('line')
    .attr('x1', x(c.median)).attr('x2', x(c.median))
    .attr('y1', innerH - 4).attr('y2', innerH + 6)
    .attr('stroke', '#1d9e75').attr('stroke-width', 1.6)
  root.append('text')
    .attr('x', x(c.median)).attr('y', innerH + 18)
    .attr('text-anchor', 'middle')
    .style('font-size', '9px').style('fill', '#1d9e75')
    .text(`med=${c.median.toFixed(2)}`)
}

watch(() => `${appState.year}|${appState.ablation}`, load)
const reload = () => load()

onMounted(() => {
  load()
  bus.on('match-accepted', reload)
  bus.on('match-restored', reload)
  window.addEventListener('resize', draw)
})
onUnmounted(() => {
  bus.off('match-accepted', reload)
  bus.off('match-restored', reload)
  window.removeEventListener('resize', draw)
})
</script>

<style lang="less" scoped>
.panel-body { display: flex; flex-direction: column; gap: 4px; }
.curve-svg { width: 100%; flex: 1 1 auto; min-height: 140px; }
.legend {
  display: flex; align-items: center; gap: 12px;
  font-size: 10px; color: #555; flex-wrap: wrap;
  .sw {
    display: inline-block; width: 14px; height: 4px; margin-right: 4px;
    vertical-align: middle;
    &.mas { background: #993c1d; }
    &.hgt { background: repeating-linear-gradient(to right, #1d9e75 0 5px, transparent 5px 9px); }
    &.hist { background: #5d839a; }
    &.meanline { width: 2px; height: 12px; background: #993c1d; }
  }
}
.footnote { padding: 0 2px; line-height: 1.35; }
.btn.ghost.tiny { font-size: 9px; padding: 1px 6px; margin-left: 4px; }
</style>
