<template>
  <div class="panel">
    <div class="panel-head">
      <span>V2 · Processed Pairs · {{ appState.year }} ({{ appState.ablation }})</span>
      <span class="tiny muted">{{ rows.length }} of {{ totalRows }} positives</span>
      <label class="tiny" style="margin-left:auto;">
        <input type="checkbox" v-model="positivesOnly" @change="load" />
        positives only
      </label>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v2')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body no-pad">
      <table class="dense">
        <thead>
          <tr>
            <th>id</th><th>husband</th><th>wife</th>
            <th class="num">score</th>
            <th class="num">gap</th>
            <th>H.</th>
            <th>era</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id"
              :class="{ active: selectedSet.has(row.id) }"
              @click="onRowClick(row)">
            <td>{{ row.id }}</td>
            <td>{{ row.male_idx }}</td>
            <td>{{ row.female_idx }}</td>
            <td class="num">{{ row.score?.toFixed(2) }}</td>
            <td class="num">{{ row.score_gap?.toFixed(2) }}</td>
            <td><span class="dot" :class="hClass(row.hungarian_correct)"></span></td>
            <td class="tiny muted">{{ row.era }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, watch, onMounted, onUnmounted } from 'vue'
import { getMatches } from '../api/client.js'
import bus from '../utils/eventbus.js'

const appState = inject('appState')
const positivesOnly = ref(true)
const rows = ref([])
const totalRows = ref(0)

const selectedSet = computed(() => new Set(appState.selectedPairIds || []))

function hClass(v) {
  if (v === true) return 'ok'
  if (v === false) return 'bad'
  return 'na'
}

async function load() {
  const list = await getMatches({
    year: appState.year, ablation: appState.ablation,
    limit: 300, positives_only: positivesOnly.value,
  })
  rows.value = list
  totalRows.value = list.length
}

function onRowClick(row) {
  bus.emit('hex-select', {
    binKey: `pt:${row.male_idx}-${row.female_idx}`,
    pairs: [row],
  })
}

watch(() => `${appState.year}|${appState.ablation}`, load)
onMounted(load)
onUnmounted(() => {})
</script>

<style lang="less" scoped>
table.dense .num { text-align: right; font-variant-numeric: tabular-nums; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; vertical-align: middle; }
.dot.ok { background: #0f6e56; }
.dot.bad { background: #993c1d; }
.dot.na { background: #d3d3d3; border: 1px solid #aaa; }
</style>
