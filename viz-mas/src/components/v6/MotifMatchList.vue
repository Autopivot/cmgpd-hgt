<template>
  <div class="motif-match-list">
    <div v-if="!husband" class="empty">
      select a husband in V4 to detect motifs
    </div>
    <div v-else-if="!candidates || candidates.length === 0" class="empty">
      no candidates
    </div>
    <div v-else-if="serviceError" class="empty error">
      motif service unavailable<span v-if="serviceErrorReason"> — {{ serviceErrorReason }}</span>
    </div>
    <div v-else-if="loading" class="empty loading">
      scanning candidates… ({{ doneCount }}/{{ candidates.length }} done)
    </div>
    <div v-else-if="rows.length === 0" class="empty">
      no motifs detected for any candidate
    </div>
    <div v-else class="card-grid">
      <div
        v-for="row in rows"
        :key="row.motif.id"
        class="motif-card"
        :title="row.motif.id"
      >
        <div class="card-top">
          <MotifMiniGlyph :motif="row.motif" :size="110" />
          <div class="motif-name">{{ row.motif.name_en || row.motif.id }}</div>
          <div class="match-line">
            <span class="match-label">matched:</span>
            <span
              v-for="wid in row.matchedCandidates"
              :key="wid"
              class="chip"
            >{{ wid }}</span>
          </div>
        </div>
        <div class="card-bottom">
          <div class="explanation">{{ row.motif.explanation_en || '' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import MotifMiniGlyph from './MotifMiniGlyph.vue'
// Use the same axios baseURL convention as src/api/client.js (which exposes
// only named exports). A thin instance pointed at /api keeps endpoints
// addressed identically to the rest of the app and rides through the Vite
// dev proxy to the FastAPI backend.
import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 30000 })

const props = defineProps({
  husband: { type: Object, default: null },     // { husband_id }
  candidates: { type: Array, default: () => [] }, // [{ wife_id, ... }]
  year: { type: Number, default: null },
})

// Memoization: key `${husband_id}|${wife_id}|${year}` → response | { _error }
const pairCache = new Map()

const loading = ref(false)
const doneCount = ref(0)
const serviceError = ref(false)
const serviceErrorReason = ref('')
// Per-pair detected motifs: Map<wife_id, details[]>
const detectedByWife = ref(new Map())

function cacheKey(h, w, y) { return `${h}|${w}|${y}` }

async function fetchPair(husband_id, wife_id, year) {
  const k = cacheKey(husband_id, wife_id, year)
  if (pairCache.has(k)) return pairCache.get(k)
  try {
    const r = await http.get(
      `/motifs/${encodeURIComponent(husband_id)}/${encodeURIComponent(wife_id)}`,
      { params: { year } }
    )
    pairCache.set(k, r.data)
    return r.data
  } catch (e) {
    const status = e?.response?.status
    const detail = e?.response?.data?.detail
    const result = {
      _error: true,
      status,
      reason: typeof detail === 'object' ? (detail?.reason || detail?.error || '') : (detail || String(e)),
    }
    pairCache.set(k, result)
    return result
  }
}

async function recompute() {
  serviceError.value = false
  serviceErrorReason.value = ''
  detectedByWife.value = new Map()
  doneCount.value = 0

  if (!props.husband?.husband_id) return
  if (!props.candidates || props.candidates.length === 0) return
  if (!props.year) return

  loading.value = true
  const husband_id = props.husband.husband_id
  const year = props.year
  const cands = [...props.candidates]

  try {
    const promises = cands.map(c =>
      fetchPair(husband_id, c.wife_id, year).then(res => {
        doneCount.value += 1
        return { wife_id: c.wife_id, res }
      })
    )
    const settled = await Promise.all(promises)

    // Surface 503 / service unavailable from any failure.
    const errored = settled.filter(s => s.res?._error)
    const got503 = errored.find(s => s.res.status === 503)
    if (got503) {
      serviceError.value = true
      serviceErrorReason.value = got503.res.reason || ''
      return
    }

    const map = new Map()
    for (const { wife_id, res } of settled) {
      if (res?._error) continue
      const details = res?.details || []
      map.set(wife_id, details)
    }
    detectedByWife.value = map
  } finally {
    loading.value = false
  }
}

// Aggregate motifId → { motif, matchedCandidates }
const rows = computed(() => {
  const agg = new Map()
  for (const [wife_id, details] of detectedByWife.value.entries()) {
    for (const d of details) {
      if (!d?.id) continue
      if (!agg.has(d.id)) {
        agg.set(d.id, { motif: d, matchedCandidates: [] })
      }
      const entry = agg.get(d.id)
      if (!entry.matchedCandidates.includes(wife_id)) {
        entry.matchedCandidates.push(wife_id)
      }
    }
  }
  return [...agg.values()].sort(
    (a, b) => b.matchedCandidates.length - a.matchedCandidates.length
  )
})

watch(
  () => [props.husband?.husband_id, props.year, props.candidates?.map(c => c.wife_id).join(',')],
  () => { recompute() },
  { immediate: true, deep: false }
)
</script>

<style lang="less" scoped>
.motif-match-list {
  display: flex;
  flex-direction: column;
  max-height: 100%;
  overflow-y: auto;
  font-family: Monaco, Menlo, monospace;
  font-size: 11px;
}
.empty {
  padding: 14px 8px;
  color: #777;
  border: 1px dashed #b8b2a3;
  background: #faf7ef;
  border-radius: 3px;
  text-align: center;
  &.error  { color: #993c1d; border-color: #d49b8d; background: #fbeee9; }
  &.loading { color: #555; }
}
/* Card grid: auto-fill columns at min 160px, equal width per column.
 * align-items: stretch keeps every card in a row at the same height as the
 * tallest card in that row; grid-auto-rows: 1fr forces equal-height rows
 * across the whole grid. Each card is itself a column flex (top + bottom)
 * so the explanation expands to fill any leftover vertical space. */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  grid-auto-rows: 1fr;
  gap: 6px;
  align-items: stretch;
}
.motif-card {
  display: flex;
  flex-direction: column;
  background: #fbf9f3;
  border: 1px solid #e2dccb;
  border-radius: 3px;
  overflow: hidden;
  min-height: 0;
}
.card-top {
  padding: 6px 6px 4px 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  border-bottom: 1px dashed #d4c8a3;
  background: #f6f1e2;
}
.motif-name {
  font-size: 10px; font-weight: 600;
  color: #4a3f2a; text-align: center;
  line-height: 1.2; word-break: break-word;
}
.match-line {
  display: flex; flex-wrap: wrap; justify-content: center;
  align-items: center; gap: 3px;
  margin-top: 2px;
}
.match-label {
  color: #666; font-size: 9px; letter-spacing: 0.3px;
}
.chip {
  display: inline-block;
  padding: 0 5px;
  background: #fff;
  border: 1px solid #c8bfa6;
  border-radius: 7px;
  font-size: 9px;
  color: #3a3a36;
  font-family: Monaco, monospace;
}
.card-bottom {
  flex: 1 1 auto;
  min-height: 0;
  padding: 5px 7px;
  overflow-y: auto;
}
.explanation {
  font-size: 10px;
  color: #444;
  line-height: 1.35;
  font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
  white-space: normal;
  word-wrap: break-word;
}
</style>
