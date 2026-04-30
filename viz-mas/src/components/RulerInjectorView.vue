<template>
  <div class="panel">
    <div class="panel-head">
      <span>V6: Rules View</span>
      <span v-if="contextSource" class="tiny muted ctx-tag">
        ctx: {{ contextSource }} · {{ candidates.length }} candidate(s)
      </span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v6')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body">
      <section class="macro">
        <h3 class="section-head">MACRO FEATURES</h3>
        <div class="macro-row">
          <MacroCombinedChart :year="appState?.year ?? 1882" />
          <PairSimilarityBarChart :husband="husband" :candidates="candidates" />
        </div>
      </section>
      <section class="micro">
        <h3 class="section-head">MICRO MOTIFS</h3>
        <MotifMatchList
          :husband="husband"
          :candidates="candidates"
          :year="appState?.year ?? 1882"
        />
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, onMounted, onUnmounted } from 'vue'
import bus from '../utils/eventbus.js'
import MacroCombinedChart from './v6/MacroCombinedChart.vue'
import PairSimilarityBarChart from './v6/PairSimilarityBarChart.vue'
import MotifMatchList from './v6/MotifMatchList.vue'

const appState = inject('appState', null)

const husband = ref(null)        // { husband_id }
const candidates = ref([])       // [{ wife_id, score?, score_gap? }, ...]
const contextSource = ref('')    // 'V5 arena' | 'V4 click' | ''

// V5 emits cohort-context after the user hits ▶ arena and the per-person
// agents are spawned — that's the canonical candidate set the user wants V6
// to analyse. V4 click also emits husband-context with the V4-cohort candidates;
// we keep that as a seed so V6 doesn't sit empty before arena starts.
function onCohortContext({ husband_id, candidate_ids }) {
  if (!husband_id || !Array.isArray(candidate_ids) || !candidate_ids.length) {
    return  // ignore the V5 clear-events; husband-context handles its own clear
  }
  husband.value = { husband_id }
  candidates.value = candidate_ids.map(id => ({ wife_id: id }))
  contextSource.value = 'V5 arena'
}
function onHusbandContext({ husband_id, candidates: cs }) {
  // Don't overwrite a V5-arena context with a V4 click for the same husband —
  // arena candidates are the authoritative set once spawned.
  if (contextSource.value === 'V5 arena' && husband.value?.husband_id === husband_id) {
    return
  }
  husband.value = husband_id ? { husband_id } : null
  candidates.value = cs || []
  contextSource.value = husband_id ? 'V4 click' : ''
}

onMounted(() => {
  bus.on('cohort-context', onCohortContext)
  bus.on('husband-context', onHusbandContext)
})
onUnmounted(() => {
  bus.off('cohort-context', onCohortContext)
  bus.off('husband-context', onHusbandContext)
})
</script>

<style lang="less" scoped>
.section-head {
  font-size: 10px; color: #444; margin: 0 0 4px 0;
  letter-spacing: 0.5px; text-transform: uppercase;
}
.ctx-tag { color: #6b5736; font-style: italic; }
section.macro { margin-bottom: 12px; }
.macro-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
  height: 180px;
  & > * { flex: 1 1 0; min-width: 0; height: 100%; }
}
</style>
