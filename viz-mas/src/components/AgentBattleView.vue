<template>
  <div class="panel">
    <div class="panel-head">
      <span>V5 · Agent Arena · MAS Negotiation</span>
      <span class="tiny muted">{{ headLabel }}</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v5')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body">
      <div v-if="!pair" class="muted tiny">
        No pair selected. Click a hex/dot in V3 or a row in V2 to start a negotiation round.
      </div>
      <div v-else>
        <div class="pair-head">
          <span class="chip">{{ pair.husband_id }}</span>
          <span class="muted">×</span>
          <span class="chip">{{ pair.wife_id }}</span>
          <span class="dot" :class="hClass(pair.hungarian_correct)" :title="hLabel(pair.hungarian_correct)"></span>
          <span class="tiny muted">score = {{ pair.score?.toFixed(2) }} · gap = {{ pair.score_gap?.toFixed(2) }}</span>
          <span class="stream-state tiny" :class="streamState">{{ streamState }}</span>
        </div>

        <!-- Streamed agent rounds -->
        <ul class="agent-list">
          <li v-for="(a, i) in rounds" :key="i" class="agent-row">
            <span class="agent-name">{{ a.agent }}</span>
            <span class="bar-track">
              <span class="bar-fill" :class="{ neg: a.score < 0 }" :style="barStyle(a.score)"></span>
            </span>
            <span class="agent-score">{{ a.score?.toFixed(2) }}</span>
            <span class="tiny muted note">{{ a.note }}</span>
          </li>
          <li v-if="finalEvt" class="final">
            <span class="agent-name">FINAL</span>
            <span class="bar-track">
              <span class="bar-fill final" :style="barStyle(finalEvt.final_score)"></span>
            </span>
            <span class="agent-score">{{ finalEvt.final_score?.toFixed(2) }}</span>
            <span class="chip" :class="finalEvt.accept ? 'accept' : 'reject'">
              {{ finalEvt.accept ? 'ACCEPT' : 'REJECT' }}
            </span>
          </li>
        </ul>

        <!-- SHAP waterfall: per-component decomposition of the final logit -->
        <div v-if="shap" class="shap-block">
          <div class="shap-head tiny">
            <strong>SHAP-style waterfall · feature attribution</strong>
            <span class="muted">Σ = {{ shapSum.toFixed(2) }} (logit)</span>
          </div>
          <svg :viewBox="`0 0 ${shapW} ${shapH}`" class="shap-svg" preserveAspectRatio="xMidYMid meet">
            <g>
              <line :x1="shapZeroX" :x2="shapZeroX" :y1="0" :y2="shapH"
                    stroke="#888780" stroke-dasharray="3 2" stroke-width="0.5" />
              <g v-for="(b, i) in shapBars" :key="i">
                <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h"
                      :fill="b.fill" :stroke="b.stroke" stroke-width="0.5"
                      :opacity="b.is_total ? 1.0 : 0.85" />
                <text :x="b.labelX" :y="b.y + b.h * 0.5 + 3"
                      :text-anchor="b.labelX < shapZeroX ? 'end' : 'start'"
                      class="shap-label">{{ b.label }}</text>
                <text :x="b.valueX" :y="b.y + b.h * 0.5 + 3"
                      :text-anchor="b.value >= 0 ? 'start' : 'end'"
                      class="shap-value">{{ b.value >= 0 ? '+' : '' }}{{ b.value.toFixed(2) }}</text>
              </g>
            </g>
          </svg>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, watch, onMounted, onUnmounted } from 'vue'
import { streamAgentRound, getShap } from '../api/client.js'
import bus from '../utils/eventbus.js'

const appState = inject('appState')
const pair = ref(null)
const rounds = ref([])
const finalEvt = ref(null)
const streamState = ref('idle')
const shap = ref(null)

let activeStream = null

const headLabel = computed(() => {
  if (!pair.value) return 'select a pair in V3 / V2'
  return `pair #${pair.value.id} · ${rounds.value.length} agent(s)`
})

function hClass(v) {
  if (v === true) return 'ok'
  if (v === false) return 'bad'
  return 'na'
}
function hLabel(v) {
  if (v === true) return 'Hungarian: correct'
  if (v === false) return 'Hungarian: wrong wife'
  return 'Hungarian: n/a (negative)'
}

// Map [-3, 8] (typical logit range) to [0, 100%].
function barWidthPct(s) {
  const lo = -3, hi = 8
  const v = Math.max(lo, Math.min(hi, s ?? 0))
  return (v - lo) / (hi - lo) * 100
}
function barStyle(s) { return { width: `${barWidthPct(s).toFixed(1)}%` } }

// ── SHAP waterfall geometry ────────────────────────────────────────
const shapW = 360
const barH = 18
const barGap = 4
const shapPadL = 110
const shapPadR = 70

const shapH = computed(() => (shap.value?.components?.length || 0) * (barH + barGap) + 8)
const shapZeroX = computed(() => {
  const c = shap.value?.components || []
  if (!c.length) return shapW / 2
  let mn = 0, mx = 0, run = 0
  for (const p of c) {
    if (p.is_total) continue
    run += p.value || 0
    mn = Math.min(mn, run)
    mx = Math.max(mx, run)
  }
  const scale = (shapW - shapPadL - shapPadR) / Math.max(1e-6, mx - mn)
  return shapPadL - mn * scale
})
const shapSum = computed(() => {
  const c = shap.value?.components || []
  return c.reduce((s, p) => s + (p.is_total ? 0 : p.value || 0), 0)
})
const shapBars = computed(() => {
  const c = shap.value?.components || []
  if (!c.length) return []
  const innerW = shapW - shapPadL - shapPadR
  // Domain: cumulative range across non-total components
  let mn = 0, mx = 0, run = 0
  for (const p of c) {
    if (p.is_total) continue
    run += p.value || 0
    mn = Math.min(mn, run); mx = Math.max(mx, run)
  }
  const scale = innerW / Math.max(1e-6, mx - mn)

  const bars = []
  let cum = 0
  c.forEach((p, i) => {
    const v = p.value || 0
    const y = i * (barH + barGap) + 4
    if (p.is_total) {
      const x0 = shapPadL - mn * scale
      const x1 = x0 + v * scale
      bars.push({
        x: Math.min(x0, x1), y, w: Math.abs(x1 - x0), h: barH,
        fill: '#1a1a1a', stroke: '#0a0a0a', is_total: true,
        label: p.label, value: v,
        labelX: shapPadL - 4, valueX: x1 + 3,
      })
      return
    }
    const x0 = shapPadL - mn * scale + cum * scale
    const x1 = x0 + v * scale
    cum += v
    bars.push({
      x: Math.min(x0, x1), y, w: Math.abs(x1 - x0), h: barH,
      fill: v >= 0 ? '#0f6e56' : '#993c1d',
      stroke: v >= 0 ? '#0a4a3a' : '#7a2a16',
      is_total: false,
      label: p.label, value: v,
      labelX: shapPadL - 4, valueX: x1 + 3,
    })
  })
  return bars
})

// ── Stream lifecycle ───────────────────────────────────────────────
function onHexSelect(payload) {
  const picks = payload?.pairs || []
  if (!picks.length) {
    pair.value = null
    rounds.value = []
    finalEvt.value = null
    return
  }
  pair.value = picks[0]
  startStream()
}

function stopStream() {
  if (activeStream) { activeStream.close(); activeStream = null }
}

async function startStream() {
  stopStream()
  rounds.value = []
  finalEvt.value = null
  shap.value = null
  if (!pair.value) return
  streamState.value = 'streaming'
  activeStream = streamAgentRound({
    year: appState.year, ablation: appState.ablation, pair_id: pair.value.id,
    onEvent: (e) => {
      if (e.event === 'agent') rounds.value = [...rounds.value, { agent: e.agent, score: e.score, note: e.note }]
      else if (e.event === 'final') finalEvt.value = e
    },
    onDone: () => { streamState.value = 'done' },
    onError: () => { streamState.value = 'error' },
  })
  // SHAP request runs in parallel with the stream.
  try {
    shap.value = await getShap({ year: appState.year, ablation: appState.ablation, pair_id: pair.value.id })
  } catch {
    shap.value = null
  }
}

// React to slider changes in V6 — re-stream the current pair so weights apply.
function onRulesUpdated() {
  if (pair.value) startStream()
}

watch(() => `${appState.year}|${appState.ablation}`, () => {
  pair.value = null
  rounds.value = []
  finalEvt.value = null
  shap.value = null
  stopStream()
})

onMounted(() => {
  bus.on('hex-select', onHexSelect)
  bus.on('rules-updated', onRulesUpdated)
})
onUnmounted(() => {
  bus.off('hex-select', onHexSelect)
  bus.off('rules-updated', onRulesUpdated)
  stopStream()
})
</script>

<style lang="less" scoped>
.pair-head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.ok { background: #0f6e56; }
.dot.bad { background: #993c1d; }
.dot.na { background: #d3d3d3; border: 1px solid #aaa; }
.stream-state {
  margin-left: auto;
  padding: 1px 6px; border-radius: 2px;
  background: #f0efe9; color: #555;
  &.streaming { background: #d4a85d; color: #1a1a1a; }
  &.done { background: #0f6e56; color: #fff; }
  &.error { background: #993c1d; color: #fff; }
}
.agent-list { display: flex; flex-direction: column; gap: 4px; padding: 4px 0; }
.agent-row, .final {
  display: grid;
  grid-template-columns: 110px 1fr 36px auto;
  gap: 6px; align-items: center;
  font-size: 11px;
}
.agent-name { color: #555; font-family: "Monaco", monospace; }
.bar-track {
  background: #f0efe9; height: 8px; border-radius: 2px; overflow: hidden;
  border: 1px solid #ddd;
}
.bar-fill { display: block; height: 100%; background: #d4a85d; }
.bar-fill.neg { background: #993c1d; }
.bar-fill.final { background: #1a1a1a; }
.agent-score { text-align: right; font-variant-numeric: tabular-nums; }
.note { padding-left: 4px; font-style: italic; }
.final .agent-name { color: #1a1a1a; font-weight: 700; }
.chip.accept { background: #0f6e56; color: #fff; }
.chip.reject { background: #993c1d; color: #fff; }

.shap-block { margin-top: 12px; border-top: 1px dashed #d4a85d; padding-top: 8px; }
.shap-head { display: flex; justify-content: space-between; margin-bottom: 4px; }
.shap-svg { width: 100%; height: auto; display: block; }
.shap-label { font-size: 9px; fill: #444; font-family: "Monaco", monospace; }
.shap-value { font-size: 9px; fill: #1a1a1a; font-family: "Monaco", monospace; font-variant-numeric: tabular-nums; }
</style>
