<template>
  <div class="panel">
    <div class="panel-head">
      <span>V5 · Agent Arena · MAS Negotiation</span>
      <span class="tiny muted">{{ pairs.length ? `pair #${pairs[0].id}` : 'select a pair in V3 / V2' }}</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v5')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body">
      <div v-if="!pairs.length" class="muted tiny">
        No pair selected. Click a hex/dot in V3 or a row in V2 to start a negotiation round.
      </div>
      <div v-else>
        <div class="pair-head">
          <span class="chip">{{ pairs[0].husband_id }}</span>
          <span class="muted">×</span>
          <span class="chip">{{ pairs[0].wife_id }}</span>
          <span :class="hClass(pairs[0].hungarian_correct)" class="dot" :title="hLabel(pairs[0].hungarian_correct)"></span>
          <span class="tiny muted">score = {{ pairs[0].score?.toFixed(2) }} · gap = {{ pairs[0].score_gap?.toFixed(2) }}</span>
        </div>
        <ul class="agent-list" v-if="round">
          <li v-for="(a, i) in round.rounds" :key="i" class="agent-row">
            <span class="agent-name">{{ a.agent }}</span>
            <span class="bar-track"><span class="bar-fill" :style="{ width: barWidth(a.score) }"></span></span>
            <span class="agent-score">{{ a.score?.toFixed(2) }}</span>
            <span class="tiny muted note">{{ a.note }}</span>
          </li>
          <li class="final">
            <span class="agent-name">FINAL</span>
            <span class="bar-track"><span class="bar-fill final" :style="{ width: barWidth(round.final_score) }"></span></span>
            <span class="agent-score">{{ round.final_score?.toFixed(2) }}</span>
            <span class="chip" :class="round.accept ? 'accept' : 'reject'">
              {{ round.accept ? 'ACCEPT' : 'REJECT' }}
            </span>
          </li>
        </ul>
        <div class="tiny muted" style="margin-top: 6px;">
          Stub: each agent is a single hand-rolled scoring rule. The live MAS+HGT
          backend (LLM negotiation rounds, motif voting, accept/reject feedback)
          is a future commit — see viz-mas/README.md.
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, watch, onMounted, onUnmounted } from 'vue'
import { getAgentRound } from '../api/client.js'
import bus from '../utils/eventbus.js'

const appState = inject('appState')
const pairs = ref([])
const round = ref(null)

function barWidth(s) {
  // Map [-3, 8] (typical logit range) to [0, 100%].
  const lo = -3, hi = 8
  const v = Math.max(lo, Math.min(hi, s ?? 0))
  return `${((v - lo) / (hi - lo) * 100).toFixed(1)}%`
}

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

async function loadRound() {
  if (!pairs.value.length) {
    round.value = null
    return
  }
  round.value = await getAgentRound({
    year: appState.year, ablation: appState.ablation,
    pair_id: pairs.value[0].id,
  })
}

function onHexSelect(payload) {
  pairs.value = payload?.pairs || []
  loadRound()
}

watch(() => `${appState.year}|${appState.ablation}`, () => {
  pairs.value = []
  round.value = null
})

onMounted(() => bus.on('hex-select', onHexSelect))
onUnmounted(() => bus.off('hex-select', onHexSelect))
</script>

<style lang="less" scoped>
.pair-head {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 6px;
}
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.ok { background: #0f6e56; }
.dot.bad { background: #993c1d; }
.dot.na { background: #d3d3d3; border: 1px solid #aaa; }
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
.bar-fill.final { background: #1a1a1a; }
.agent-score { text-align: right; font-variant-numeric: tabular-nums; }
.note { padding-left: 4px; font-style: italic; }
.final .agent-name { color: #1a1a1a; font-weight: 700; }
.chip.accept { background: #0f6e56; color: #fff; }
.chip.reject { background: #993c1d; color: #fff; }
</style>
