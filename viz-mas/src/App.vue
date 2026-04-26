<template>
  <div class="container">
    <div class="title-bar">
      <div class="title">CMGPD MAS · Hex Analytics</div>
      <div class="cohort-config">
        <span class="lbl">YEAR</span>
        <div class="seg">
          <button v-for="y in ALL_YEARS" :key="y" :class="{ active: state.year === y }"
                  @click="setYear(y)">{{ y }}</button>
        </div>
        <span class="lbl">COND</span>
        <div class="seg">
          <button :class="{ active: state.ablation === 'ablated' }"
                  @click="setAblation('ablated')">ablated</button>
          <button :class="{ active: state.ablation === 'unablated' }"
                  @click="setAblation('unablated')">unablated</button>
        </div>
        <span class="lbl">LLM</span>
        <input class="mini-input model" v-model="llmModel"
               placeholder="qwen-plus-2025-04-28" @change="saveLLM" />
        <input class="mini-input key" :type="showKey ? 'text' : 'password'"
               v-model="llmKey" placeholder="DashScope API key" @change="saveLLM" />
        <button class="eye" @click="showKey = !showKey" :title="showKey ? 'hide' : 'show'">
          {{ showKey ? '●' : '○' }}
        </button>
        <span class="llm-status" :class="{ on: llmUseLLM }">
          {{ llmUseLLM ? 'llm' : 'stub' }}
        </span>
      </div>
      <div class="actions">
        <span class="status" :class="{ ok: healthy }">{{ healthy ? 'backend ok' : 'static data' }}</span>
        <button class="btn" @click="resetSelection">Reset</button>
      </div>
    </div>
    <div class="body">
      <!-- Column 1 (3/12) -->
      <div class="col col-left">
        <div class="cell cell-upper" :class="{ fullscreen: state.fullscreen === 'v1' }"><OverviewView /></div>
        <div class="cell cell-lower" :class="{ fullscreen: state.fullscreen === 'v2' }"><ProcessedRelationsTable /></div>
      </div>
      <!-- Column 2 (5/12) -->
      <div class="col col-mid">
        <div class="cell cell-upper" :class="{ fullscreen: state.fullscreen === 'v3' }"><HexEmbeddingView /></div>
        <div class="cell cell-lower" :class="{ fullscreen: state.fullscreen === 'v4' }"><BipartiteDetailView /></div>
      </div>
      <!-- Column 3 (4/12) -->
      <div class="col col-right">
        <div class="cell cell-upper" :class="{ fullscreen: state.fullscreen === 'v5' }"><AgentBattleView /></div>
        <div class="cell cell-lower" :class="{ fullscreen: state.fullscreen === 'v6' }"><RulerInjectorView /></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, nextTick, onMounted, onUnmounted, provide } from 'vue'
import OverviewView from './components/OverviewView.vue'
import ProcessedRelationsTable from './components/ProcessedRelationsTable.vue'
import HexEmbeddingView from './components/HexEmbeddingView.vue'
import BipartiteDetailView from './components/BipartiteDetailView.vue'
import AgentBattleView from './components/AgentBattleView.vue'
import RulerInjectorView from './components/RulerInjectorView.vue'
import { health, ALL_YEARS, getLLMConfig, setLLMConfig } from './api/client.js'
import bus from './utils/eventbus.js'

// Single global cohort state. Provided to all child views via `inject('appState')`.
const state = reactive({
  year: 1882,
  ablation: 'ablated',
  fullscreen: null,
  selectedPairIds: [],   // set by lasso/hex-select in V3, consumed by V4/V5
})
provide('appState', state)

const healthy = ref(false)
let tick = null

// LLM config (per-person Qwen agent in V5)
const llmModel = ref('qwen-plus-2025-04-28')
const llmKey = ref('')
const llmUseLLM = ref(false)
const showKey = ref(false)

async function loadLLM() {
  try {
    const c = await getLLMConfig()
    llmModel.value = c.model || 'qwen-plus-2025-04-28'
    llmUseLLM.value = !!c.use_llm
  } catch {}
  // Restore key from localStorage if present (server only keeps in-memory).
  const saved = localStorage.getItem('cmgpd-dashscope-key') || ''
  if (saved && !llmUseLLM.value) {
    llmKey.value = saved
    await saveLLM()
  }
}
async function saveLLM() {
  try {
    const body = { model: llmModel.value }
    if (llmKey.value) body.api_key = llmKey.value
    const c = await setLLMConfig(body)
    llmUseLLM.value = !!c.use_llm
    if (llmKey.value) localStorage.setItem('cmgpd-dashscope-key', llmKey.value)
  } catch (e) { console.warn('setLLMConfig failed', e) }
}

function notifyResize() {
  nextTick(() => window.dispatchEvent(new Event('resize')))
}

function setYear(y) {
  if (state.year === y) return
  state.year = y
  state.selectedPairIds = []
  bus.emit('cohort-changed', { year: y, ablation: state.ablation })
}
function setAblation(a) {
  if (state.ablation === a) return
  state.ablation = a
  state.selectedPairIds = []
  bus.emit('cohort-changed', { year: state.year, ablation: a })
}
function resetSelection() {
  state.selectedPairIds = []
  bus.emit('hex-clear')
}

function handleFullScreen(id) {
  state.fullscreen = state.fullscreen === id ? null : id
  notifyResize()
}
function handleKeydown(e) {
  if (e.key === 'Escape' && state.fullscreen) {
    state.fullscreen = null
    notifyResize()
  }
}
function handleHexSelect(payload) {
  state.selectedPairIds = (payload?.pairs || []).map(p => p.id)
}

async function probe() {
  healthy.value = await health()
}

onMounted(() => {
  probe()
  loadLLM()
  tick = setInterval(probe, 8000)
  bus.on('full-screen', handleFullScreen)
  bus.on('hex-select', handleHexSelect)
  bus.on('hex-clear', () => { state.selectedPairIds = [] })
  window.addEventListener('keydown', handleKeydown)
  // Kick the initial cohort load.
  bus.emit('cohort-changed', { year: state.year, ablation: state.ablation })
})
onUnmounted(() => {
  clearInterval(tick)
  bus.off('full-screen', handleFullScreen)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style lang="less" scoped>
.container {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #a8a8a8;
}
.title-bar {
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  background: #1a1a1a;
  color: #fafafa;
  gap: 12px;
  border-bottom: 2px solid #d4a85d;

  .title { font-size: 14px; font-weight: 600; letter-spacing: 0.4px; flex: 0 0 auto; color: #f3ecdf; }
  .cohort-config {
    flex: 1 1 auto;
    display: flex; align-items: center; gap: 6px;
    font-size: 10px;
    flex-wrap: wrap;
    .lbl { color: #9b9b9b; letter-spacing: 0.6px; }
    .seg {
      background: #2a2a2a;
      border: 1px solid #555;
      > button {
        background: #2a2a2a;
        color: #eaeaea;
        border-right-color: #555;
        &:hover { background: #353535; }
        &.active { background: #d4a85d; color: #1a1a1a; }
      }
    }
    .mini-input {
      height: 22px; background: #2a2a2a; color: #eaeaea;
      border: 1px solid #555; border-radius: 3px;
      padding: 0 6px; font-size: 10px;
      font-family: "Monaco", "Menlo", "Consolas", monospace;
    }
    .mini-input.model { width: 130px; }
    .mini-input.key { flex: 0 1 200px; min-width: 100px; }
    .mini-input:focus { border-color: #ffd166; outline: none; }
    .eye {
      width: 22px; height: 22px; border: 1px solid #555; background: #2a2a2a;
      color: #eaeaea; border-radius: 3px; cursor: pointer; font-size: 12px; line-height: 1;
    }
    .llm-status {
      font-size: 9px; padding: 2px 6px; border-radius: 2px;
      color: #9b9b9b; border: 1px solid #555;
      &.on { color: #1a1a1a; background: #8aff96; border-color: #3a7a46; }
    }
  }
  .actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
  .status {
    font-size: 10px;
    padding: 2px 8px;
    border: 1px solid #6b6b6b;
    color: #9b9b9b;
    border-radius: 3px;
    &.ok { color: #d4a85d; border-color: #d4a85d; }
  }
  .btn { font-size: 10px; padding: 3px 8px; }
}
.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 3fr 5fr 4fr;
  gap: 8px;
  padding: 8px;
}
.col {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  min-height: 0;
}
.cell { min-height: 0; flex: 1; }
.col-left .cell-upper { flex: 0 0 40%; }
.col-left .cell-lower { flex: 1; }
.col-mid .cell-upper { flex: 0 0 62%; }
.col-mid .cell-lower { flex: 1; }
.col-right .cell-upper { flex: 0 0 55%; }
.col-right .cell-lower { flex: 1; }
</style>
