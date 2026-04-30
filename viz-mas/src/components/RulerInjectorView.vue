<template>
  <div class="panel">
    <div class="panel-head">
      <span>V6: Rules View</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v6')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body">
      <section class="macro">
        <h3 class="section-head">MACRO FEATURES</h3>
        <div class="macro-row">
          <MacroGrainChart :year="appState?.year ?? 1882" />
          <MacroDisasterChart :year="appState?.year ?? 1882" />
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
import MacroGrainChart from './v6/MacroGrainChart.vue'
import MacroDisasterChart from './v6/MacroDisasterChart.vue'
import PairSimilarityBarChart from './v6/PairSimilarityBarChart.vue'
import MotifMatchList from './v6/MotifMatchList.vue'

const appState = inject('appState', null)

const husband = ref(null)        // { husband_id }
const candidates = ref([])       // [{ wife_id, score, score_gap }, ...]
function onHusbandContext({ husband_id, candidates: cs }) {
  husband.value = husband_id ? { husband_id } : null
  candidates.value = cs || []
}

onMounted(() => bus.on('husband-context', onHusbandContext))
onUnmounted(() => bus.off('husband-context', onHusbandContext))
</script>

<style lang="less" scoped>
.section-head {
  font-size: 10px; color: #444; margin: 0 0 4px 0;
  letter-spacing: 0.5px; text-transform: uppercase;
}
section.macro { margin-bottom: 12px; }
.macro-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
  height: 180px;
  & > * { flex: 1 1 0; min-width: 0; height: 100%; }
}
</style>
