<template>
  <div class="container">
    <div class="title-bar">
      <div class="title">GeneaLink</div>
      <div class="cohort-config">
        <span class="lbl">YEAR</span>
        <div class="seg">
          <button v-for="y in ALL_YEARS" :key="y" :class="{ active: state.year === y }"
                  @click="setYear(y)">{{ y }}</button>
        </div>
      </div>
      <div class="actions">
        <span class="status" :class="{ ok: healthy }">{{ healthy ? 'backend ok' : 'static data' }}</span>
        <div class="key-popover">
          <button class="btn key-btn" :class="{ ok: llmUseLLM, missing: !llmUseLLM }"
                  :title="llmUseLLM ? 'DashScope API key set' : 'Set DashScope API key'"
                  @click="keyOpen = !keyOpen">🔑</button>
          <div v-if="keyOpen" class="key-card">
            <div class="key-row">
              <span class="tiny muted">model</span>
              <code class="model-pin">qwen3.6-plus</code>
            </div>
            <div class="key-row">
              <span class="tiny muted">DashScope key</span>
              <input class="mini-input key" :type="showKey ? 'text' : 'password'"
                     v-model="llmKey" placeholder="sk-…"
                     @keydown.enter="commitKey" />
              <button class="eye" @click="showKey = !showKey"
                      :title="showKey ? 'hide' : 'show'">{{ showKey ? '●' : '○' }}</button>
            </div>
            <div class="key-row right">
              <span class="llm-status tiny" :class="{ on: llmUseLLM }">
                {{ llmUseLLM ? 'llm' : 'stub' }}
              </span>
              <button class="btn" @click="commitKey">Save</button>
              <button class="btn ghost" @click="keyOpen = false">Close</button>
            </div>
          </div>
        </div>
        <button class="btn" @click="resetSelection">Reset</button>
      </div>
    </div>
    <div class="body" ref="bodyRef">
      <div class="col col-left" :style="{ flexBasis: colPct[0] + '%' }">
        <div class="cell cell-upper" :class="{ fullscreen: state.fullscreen === 'v1' }"
             :style="{ flexBasis: rowPct[0] + '%' }"><OverviewView /></div>
        <div class="gutter-h" @mousedown="startDragRow(0, $event)" title="drag to resize"></div>
        <div class="cell cell-lower" :class="{ fullscreen: state.fullscreen === 'v2' }"><ProcessedRelationsTable /></div>
      </div>
      <div class="gutter" @mousedown="startDrag(0, $event)" title="drag to resize"></div>
      <div class="col col-mid" :style="{ flexBasis: colPct[1] + '%' }">
        <div class="cell cell-upper" :class="{ fullscreen: state.fullscreen === 'v3' }"
             :style="{ flexBasis: rowPct[1] + '%' }"><HexEmbeddingView /></div>
        <div class="gutter-h" @mousedown="startDragRow(1, $event)" title="drag to resize"></div>
        <div class="cell cell-lower" :class="{ fullscreen: state.fullscreen === 'v4' }"><BipartiteDetailView /></div>
      </div>
      <div class="gutter" @mousedown="startDrag(1, $event)" title="drag to resize"></div>
      <div class="col col-right" :style="{ flexBasis: colPct[2] + '%' }">
        <div class="cell cell-upper" :class="{ fullscreen: state.fullscreen === 'v5' }"
             :style="{ flexBasis: rowPct[2] + '%' }"><AgentBattleView /></div>
        <div class="gutter-h" @mousedown="startDragRow(2, $event)" title="drag to resize"></div>
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

const COL_KEY = 'cmgpd-col-pct-v1'
const ROW_KEY = 'cmgpd-row-pct-v1'
const MIN_PCT = 8
const MIN_ROW_PCT = 10
const bodyRef = ref(null)

function loadPct(key, defaults) {
  try {
    const s = JSON.parse(localStorage.getItem(key) || 'null')
    if (Array.isArray(s) && s.length === defaults.length && s.every(n => typeof n === 'number')) return s
  } catch {}
  return [...defaults]
}
const colPct = ref(loadPct(COL_KEY, [20, 42, 38]))
const rowPct = ref(loadPct(ROW_KEY, [40, 75, 62]))

function makeDragger({ axis, pct, key, min, getRect, applyDelta, notifyCols }) {
  let st = null
  const cursor = axis === 'x' ? 'col-resize' : 'row-resize'
  function onMove(e) {
    if (!st) return
    const delta = ((axis === 'x' ? e.clientX - st.start : e.clientY - st.start) / st.size) * 100
    const next = applyDelta(st.base, delta, st.idx, min)
    if (next) pct.value = next
  }
  function stop() {
    if (!st) return
    const before = st.snapshot
    const movedIdx = st.idx
    st = null
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', stop)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    try { localStorage.setItem(key, JSON.stringify(pct.value)) } catch {}
    const changed = pct.value.some((v, i) => v !== before[i])
    if (changed) notifyResizeFor(...notifyCols(movedIdx))
  }
  function start(idx, e) {
    e.preventDefault()
    const rect = getRect(idx, e)
    st = {
      idx,
      start: axis === 'x' ? e.clientX : e.clientY,
      size: axis === 'x' ? rect.width : rect.height,
      base: axis === 'x' ? [...pct.value] : pct.value[idx],
      snapshot: [...pct.value],
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', stop)
    document.body.style.cursor = cursor
    document.body.style.userSelect = 'none'
  }
  return { start, stop, isActive: () => st != null }
}

const colDragger = makeDragger({
  axis: 'x',
  pct: colPct,
  key: COL_KEY,
  min: MIN_PCT,
  getRect: () => bodyRef.value.getBoundingClientRect(),
  applyDelta: (base, d, idx, min) => {
    const a = base[idx] + d, b = base[idx + 1] - d
    if (a < min || b < min) return null
    const next = [...base]; next[idx] = a; next[idx + 1] = b
    return next
  },
  notifyCols: (idx) => [idx, idx + 1],
})
const rowDragger = makeDragger({
  axis: 'y',
  pct: rowPct,
  key: ROW_KEY,
  min: MIN_ROW_PCT,
  getRect: (_idx, e) => e.currentTarget.parentElement.getBoundingClientRect(),
  applyDelta: (base, d, idx, min) => {
    const v = base + d
    if (v < min || v > 100 - min) return null
    const next = [...rowPct.value]; next[idx] = v
    return next
  },
  notifyCols: (idx) => [idx],
})
const startDrag = colDragger.start
const startDragRow = rowDragger.start

const healthy = ref(false)
let tick = null

// LLM config (per-person Qwen agent in V5)
const llmModel = ref('qwen3.6-plus')
const llmKey = ref('')
const llmUseLLM = ref(false)
const showKey = ref(false)
const keyOpen = ref(false)

async function commitKey() {
  await saveLLM()
  if (llmUseLLM.value) keyOpen.value = false
}

async function loadLLM() {
  try {
    const c = await getLLMConfig()
    llmModel.value = c.model || 'qwen3.6-plus'
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

const COL_VIEWS = [['v1', 'v2'], ['v3', 'v4'], ['v5', 'v6']]
function notifyResizeFor(...colIdxs) {
  nextTick(() => {
    const ids = new Set()
    for (const i of colIdxs) {
      if (COL_VIEWS[i]) COL_VIEWS[i].forEach(v => ids.add(v))
    }
    bus.emit('panel-resized', { ids: Array.from(ids) })
  })
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
  if (colDragger.isActive()) colDragger.stop()
  if (rowDragger.isActive()) rowDragger.stop()
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
  .key-popover { position: relative; display: inline-block; }
  .key-btn {
    background: #2a2a2a; color: #eaeaea; border: 1px solid #555;
    border-radius: 3px; padding: 2px 6px; cursor: pointer;
    &.ok { border-color: #3a7a46; }
    &.missing { border-color: #c97a4d; }
  }
  .key-card {
    position: absolute; top: 28px; right: 0; z-index: 50;
    background: #1f1f1f; color: #eaeaea;
    border: 1px solid #d4a85d; border-radius: 4px;
    padding: 8px 10px; min-width: 280px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.4);
    display: flex; flex-direction: column; gap: 6px;
    .key-row { display: flex; align-items: center; gap: 6px; }
    .key-row.right { justify-content: flex-end; }
    .model-pin {
      background: #2a2a2a; color: #d4a85d;
      padding: 1px 6px; border-radius: 2px; font-size: 10px;
      font-family: Monaco, monospace;
    }
    .mini-input.key {
      flex: 1 1 auto; height: 22px; background: #2a2a2a; color: #eaeaea;
      border: 1px solid #555; border-radius: 3px; padding: 0 6px;
      font-size: 10px; font-family: Monaco, monospace;
      &:focus { border-color: #ffd166; outline: none; }
    }
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
}
.body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  gap: 0;
  padding: 8px;
}
.col {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
  min-height: 0;
  flex: 0 0 auto;
}
.gutter {
  flex: 0 0 8px;
  margin: 0 1px;
  cursor: col-resize;
  background: transparent;
  position: relative;
  &:hover, &:active {
    background: rgba(212, 168, 93, 0.35);
  }
  &::before {
    content: '';
    position: absolute;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 2px; height: 36px;
    background: #6b6b6b;
    border-radius: 1px;
    opacity: 0.5;
  }
  &:hover::before { background: #d4a85d; opacity: 1; }
}
.cell { min-height: 0; min-width: 0; }
.cell-upper { flex: 0 0 auto; }
.cell-lower { flex: 1 1 auto; }
.gutter-h {
  flex: 0 0 8px;
  margin: 1px 0;
  cursor: row-resize;
  background: transparent;
  position: relative;
  &:hover, &:active {
    background: rgba(212, 168, 93, 0.35);
  }
  &::before {
    content: '';
    position: absolute;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 36px; height: 2px;
    background: #6b6b6b;
    border-radius: 1px;
    opacity: 0.5;
  }
  &:hover::before { background: #d4a85d; opacity: 1; }
}
</style>
