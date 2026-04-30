<template>
  <div class="panel">
    <div class="panel-head">
      <span>V6: Rules View</span>
      <span v-if="contextSource" class="tiny muted ctx-tag">
        ctx: {{ contextSource }} · {{ candidates.length }} candidate(s)
      </span>
      <span v-if="currentCellId != null" class="cell-chip tiny" :title="cellChipTitle">
        cell #{{ currentCellId }} ·
        <template v-if="cellRules && (cellRules.n_husbands ?? 0) > 0">
          {{ cellRules.n_husbands }} bound · last saved {{ cellRules.updated_at }}
        </template>
        <template v-else>unbound</template>
      </span>
      <button
        v-if="canSaveCell"
        class="cell-save-btn"
        @click="saveCellRules"
        :disabled="saving"
        :title="`Aggregate ${cellPairIds.length} pair(s) of per-husband rule weights into this cell's rule profile (year 1882).`"
      >{{ saving ? '… saving' : '💾 save to cell' }}</button>
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
import { ref, computed, inject, onMounted, onUnmounted, watch } from 'vue'
import bus from '../utils/eventbus.js'
import MacroCombinedChart from './v6/MacroCombinedChart.vue'
import PairSimilarityBarChart from './v6/PairSimilarityBarChart.vue'
import MotifMatchList from './v6/MotifMatchList.vue'
import { getCellRules, postCellRules } from '../api/client.js'

const appState = inject('appState', null)

const husband = ref(null)        // { husband_id }
const candidates = ref([])       // [{ wife_id, score?, score_gap? }, ...]
const contextSource = ref('')    // 'V5 arena' | 'V4 click' | ''

// ── F2 cell-binding state ────────────────────────────────────────────────
// `currentCellId` is the V3 hex cell whose pairs are currently surfaced in
// V4/V5/V6. We always read+write the 1882 cell-rules profile (regardless
// of the active cohort year) — F1 only allows editing in 1882, and 1885+
// is read-only and pre-fills from the saved 1882 profile so reviewers see
// the exact rule snapshot the analyst trained on.
const currentCellId = ref(null)
const cellPairIds = ref([])      // husband_ids in the current hex cell (raw .pairs[i].husband_id)
const cellPairKeys = ref([])     // `${husband_id}|${wife_id}` strings for membership tests
const cellRules = ref(null)      // server payload for cell #currentCellId @ year=1882
const saving = ref(false)

const HUSBAND_RULES_PREFIX = 'cmgpd-cell-rules-husband-'

// Save button only when authoring is allowed (1882) and we have a cell.
const canSaveCell = computed(
  () => (appState?.year ?? 1882) === 1882 && currentCellId.value != null
)

const cellChipTitle = computed(() => {
  if (!cellRules.value) return 'No saved rule profile for this hex cell yet.'
  const n = cellRules.value.n_husbands ?? 0
  return `cell #${currentCellId.value}: aggregated from ${n} per-husband rule sheet(s); last saved ${cellRules.value.updated_at}`
})

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

// V3 emits hex-select with { cell_id, pairIds, pairs } when a hex cell
// is clicked. F2 binds rule profiles to that cell id.
function onHexSelect(payload) {
  if (!payload || payload.cell_id == null) return
  currentCellId.value = payload.cell_id
  const pairs = Array.isArray(payload.pairs) ? payload.pairs : []
  cellPairIds.value = pairs.map(p => p?.husband_id).filter(v => v != null)
  cellPairKeys.value = pairs
    .filter(p => p && p.husband_id != null && p.wife_id != null)
    .map(p => `${p.husband_id}|${p.wife_id}`)
  // Always pull the 1882 profile — that's the canonical edit year.
  refreshCellRules()
}

function onHexClear() {
  currentCellId.value = null
  cellPairIds.value = []
  cellPairKeys.value = []
  cellRules.value = null
}

async function refreshCellRules() {
  if (currentCellId.value == null) {
    cellRules.value = null
    return
  }
  const cid = currentCellId.value
  const data = await getCellRules({ cell_id: cid, year: 1882 })
  // Guard against late responses for a stale cell.
  if (currentCellId.value !== cid) return
  cellRules.value = data
  // In 1885+ mode, surface the saved profile so F1's read-only sliders
  // pick it up. F1 listens for `cell-rules-updated`.
  if ((appState?.year ?? 1882) !== 1882 && data) {
    bus.emit('cell-rules-updated', {
      cell_id: cid,
      year: 1882,
      weights: data.weights || {},
      motifs_enabled: data.motifs_enabled || {},
      n_husbands: data.n_husbands ?? 0,
      updated_at: data.updated_at || null,
    })
  }
}

// Aggregate per-husband rule sheets (F1 writes to localStorage under
// `cmgpd-cell-rules-husband-{husband_id}` as {weights, motifs_enabled})
// into a single per-cell profile. Strategy:
//   • Mean-reduce numeric weights (per-key independently, so missing keys
//     in some sheets don't penalise others).
//   • OR-reduce motif booleans — if any husband in the cell flagged a
//     motif as enabled, the cell-level profile keeps it enabled.
function _aggregateHusbandRules(husbandIds) {
  const weightSums = {}
  const weightCounts = {}
  const motifsAny = {}
  let n = 0
  const seen = new Set()
  for (const hid of husbandIds) {
    if (hid == null || seen.has(hid)) continue
    seen.add(hid)
    let raw
    try {
      raw = localStorage.getItem(`${HUSBAND_RULES_PREFIX}${hid}`)
    } catch { raw = null }
    if (!raw) continue
    let parsed
    try { parsed = JSON.parse(raw) } catch { continue }
    if (!parsed || typeof parsed !== 'object') continue
    n += 1
    const w = parsed.weights || {}
    for (const k of Object.keys(w)) {
      const v = Number(w[k])
      if (!Number.isFinite(v)) continue
      weightSums[k] = (weightSums[k] || 0) + v
      weightCounts[k] = (weightCounts[k] || 0) + 1
    }
    const m = parsed.motifs_enabled || {}
    for (const k of Object.keys(m)) {
      motifsAny[k] = !!motifsAny[k] || !!m[k]
    }
  }
  const weights = {}
  for (const k of Object.keys(weightSums)) {
    weights[k] = weightSums[k] / Math.max(1, weightCounts[k])
  }
  return { weights, motifs_enabled: motifsAny, n_husbands: n }
}

async function saveCellRules() {
  if (!canSaveCell.value || saving.value) return
  saving.value = true
  try {
    const cid = currentCellId.value
    const agg = _aggregateHusbandRules(cellPairIds.value)
    await postCellRules({
      cell_id: cid,
      year: 1882,
      n_husbands: agg.n_husbands,
      weights: agg.weights,
      motifs_enabled: agg.motifs_enabled,
    })
    await refreshCellRules()
  } catch (e) {
    console.warn('postCellRules failed', e)
  } finally {
    saving.value = false
  }
}

// When the cohort year flips into 1885+ for an already-selected cell,
// re-fetch so F1 receives the read-only fill.
watch(
  () => `${appState?.year ?? 1882}|${currentCellId.value}`,
  () => { if (currentCellId.value != null) refreshCellRules() }
)

onMounted(() => {
  bus.on('cohort-context', onCohortContext)
  bus.on('husband-context', onHusbandContext)
  bus.on('hex-select', onHexSelect)
  bus.on('hex-clear', onHexClear)
})
onUnmounted(() => {
  bus.off('cohort-context', onCohortContext)
  bus.off('husband-context', onHusbandContext)
  bus.off('hex-select', onHexSelect)
  bus.off('hex-clear', onHexClear)
})
</script>

<style lang="less" scoped>
.section-head {
  font-size: 10px; color: #444; margin: 0 0 4px 0;
  letter-spacing: 0.5px; text-transform: uppercase;
}
.ctx-tag { color: #6b5736; font-style: italic; }
.cell-chip {
  margin-left: 6px;
  padding: 1px 6px;
  border: 1px solid #c8bfa8;
  border-radius: 8px;
  background: #f5f1e8;
  color: #4a3f2a;
  font-variant-numeric: tabular-nums;
}
.cell-save-btn {
  margin-left: 4px;
  font-size: 10px;
  padding: 1px 6px;
  border: 1px solid #5a7a90;
  border-radius: 3px;
  background: #eef3f7;
  color: #1a1a1a;
  cursor: pointer;
  &:hover:not(:disabled) { background: #ffe082; border-color: #d4a85d; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
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
