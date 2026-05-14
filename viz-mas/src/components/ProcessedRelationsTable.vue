<template>
  <div class="panel">
    <div class="panel-head">
      <span>{{ T.panel.v2 }}</span>
      <span class="tiny muted">{{ rows.length }} accepted</span>
      <label class="tiny gt-toggle" title="Reveal whether the accepted edge is the true r_hw (GT)">
        <input type="checkbox" v-model="showGT" /> show GT
      </label>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v2')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body no-pad">
      <table class="dense">
        <thead>
          <tr>
            <th>husband</th>
            <th>wife</th>
            <th class="num">score</th>
            <th class="num">gap</th>
            <th>H.</th>
            <th v-if="showGT">GT</th>
            <th>source</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!rows.length">
            <td :colspan="showGT ? 8 : 7" class="muted tiny" style="padding:6px 8px">
              no accepted matches yet — accept from V4 batch or V5 arena to log here
            </td>
          </tr>
          <tr v-for="row in rows" :key="row.husband_id"
              :class="{ active: selectedSet.has(row.husband_id) }"
              @click="onRowClick(row)">
            <td>{{ row.husband_id }}</td>
            <td>{{ row.wife_id }}</td>
            <td class="num">{{ formatScore(row.score) }}</td>
            <td class="num">{{ formatScore(row.score_gap) }}</td>
            <td><span class="dot" :class="hClass(row.hungarian_correct)"></span></td>
            <td v-if="showGT">
              <span v-if="row.gt_label === 1" class="gt-chip gt-yes">GT</span>
              <span v-else-if="row.gt_label === 0" class="gt-chip gt-no">neg</span>
              <span v-else class="gt-chip gt-na">—</span>
            </td>
            <td>
              <span v-for="lbl in row.source_labels" :key="lbl"
                    class="src-chip" :class="'src-' + lbl.toLowerCase()">{{ lbl }}</span>
            </td>
            <td>
              <button class="restore-btn tiny"
                      :disabled="restoring === row.husband_id"
                      :title="`Roll back the accept for ${row.husband_id}`"
                      @click.stop="onRestore(row)">
                {{ restoring === row.husband_id ? '…' : '↶ restore' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, watch, onMounted, onUnmounted } from 'vue'
import { getAccepted, restoreMatch, loadCohort } from '../api/client.js'
import bus from '../utils/eventbus.js'

const appState = inject('appState')
const T = inject('T', { panel: { v2: 'B: Process View' } })
const accepted = ref({})       // { husband_id → record }
const cohort = ref(null)       // current cohort JSON for source-tag computation
const restoring = ref(null)    // husband_id currently being restored

// Reveal-GT toggle persists per browser. Off by default — historians who
// want a blind triage shouldn't see the answer until they ask for it.
const GT_KEY = 'cmgpd-v2-show-gt'
const showGT = ref(localStorage.getItem(GT_KEY) === '1')
watch(showGT, v => { try { localStorage.setItem(GT_KEY, v ? '1' : '0') } catch {} })

const selectedSet = computed(() => new Set(appState.selectedPairIds || []))

// One-pass cohort indexing: {husband_id → HGT-top pair} and {h|w → pair}.
// Eliminates the O(rows × pairs) scans the rows computed used to do.
const cohortIndex = computed(() => {
  const top = new Map()
  const byHW = new Map()
  for (const p of (cohort.value?.pairs || [])) {
    byHW.set(`${p.husband_id}|${p.wife_id}`, p)
    const cur = top.get(p.husband_id)
    if (!cur || (p.score ?? -Infinity) > (cur.score ?? -Infinity)) {
      top.set(p.husband_id, p)
    }
  }
  return { top, byHW }
})

// ── Source labels: ["HGT"] | ["MAS"] | ["HGT", "MAS"] ──
function sourceLabelsFor(rec) {
  const src = String(rec.source || '').toLowerCase()
  const isBatch = src.includes('batch')
  const hgtTop = cohortIndex.value.top.get(rec.husband_id)
  const isHGTtop = hgtTop && hgtTop.wife_id === rec.wife_id
  const labels = []
  if (isBatch) {
    // V4 batch always picks HGT's argmax → just "HGT".
    labels.push('HGT')
  } else {
    if (isHGTtop) labels.push('HGT')   // MAS converged on HGT's top pick → both
    labels.push('MAS')
  }
  return labels
}

// ── Visible rows: filtered to current cohort, enriched with cohort joins ──
const rows = computed(() => {
  const byHW = cohortIndex.value.byHW
  const out = []
  for (const rec of Object.values(accepted.value)) {
    if (rec.year != null && rec.year !== appState.year) continue
    if (rec.ablation && rec.ablation !== appState.ablation) continue
    const p = byHW.get(`${rec.husband_id}|${rec.wife_id}`)
    out.push({
      ...rec,
      hungarian_correct: p?.hungarian_correct ?? null,
      score_gap: p?.score_gap ?? null,
      gt_label: p?.label ?? null,
      source_labels: sourceLabelsFor(rec),
    })
  }
  return out.sort((a, b) => (b.ts || 0) - (a.ts || 0))    // newest first
})

function hClass(v) {
  if (v === true) return 'ok'
  if (v === false) return 'bad'
  return 'na'
}

function formatScore(s) {
  return (typeof s === 'number') ? s.toFixed(2) : '—'
}

async function load() {
  const [c, a] = await Promise.all([
    loadCohort(appState.year, appState.ablation),
    getAccepted(),
  ])
  cohort.value = c
  accepted.value = a
}

function onRowClick(row) {
  bus.emit('hex-select', {
    binKey: `accept:${row.husband_id}-${row.wife_id}`,
    pairs: [{
      husband_id: row.husband_id, wife_id: row.wife_id,
      score: row.score, score_gap: row.score_gap,
      hungarian_correct: row.hungarian_correct,
    }],
  })
}

async function onRestore(row) {
  if (restoring.value) return
  restoring.value = row.husband_id
  // Remove locally + broadcast first so V1/V3 update even if the backend has
  // no record (e.g. accept was bus-only, or the dev backend was restarted).
  const { [row.husband_id]: _gone, ...rest } = accepted.value
  accepted.value = rest
  bus.emit('match-restored', { husband_id: row.husband_id, wife_id: row.wife_id })
  try {
    await restoreMatch(row.husband_id)
  } catch (e) {
    // 404 from the backend = nothing to undo there; the local rollback above
    // is still correct, so swallow it. Other errors get logged but don't
    // re-add the row (the user clicked restore for a reason).
    if (e?.response?.status !== 404) console.warn('restore failed', e)
  } finally {
    restoring.value = null
  }
}

function onMatchAccepted(evt) {
  if (!evt || !evt.husband_id) return
  // Patch the local map so the row appears immediately without a round-trip.
  accepted.value = {
    ...accepted.value,
    [evt.husband_id]: {
      husband_id: evt.husband_id,
      wife_id: evt.wife_id,
      score: evt.score,
      source: evt.source || 'user-accept',
      year: appState.year,
      ablation: appState.ablation,
      ts: Date.now() / 1000,
    },
  }
}

watch(() => `${appState.year}|${appState.ablation}`, load)
onMounted(() => {
  bus.on('match-accepted', onMatchAccepted)
  load()
})
onUnmounted(() => {
  bus.off('match-accepted', onMatchAccepted)
})
</script>

<style lang="less" scoped>
table.dense .num { text-align: right; font-variant-numeric: tabular-nums; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; vertical-align: middle; }
.dot.ok { background: #0f6e56; }
.dot.bad { background: #993c1d; }
.dot.na { background: #d3d3d3; border: 1px solid #aaa; }

.src-chip {
  display: inline-block;
  font-size: 9px;
  padding: 1px 5px;
  margin-right: 3px;
  border-radius: 3px;
  font-weight: 600;
  letter-spacing: 0.3px;
  font-family: Monaco, monospace;
}
.src-chip.src-hgt { background: #d4e8df; color: #0a4a3a; border: 1px solid #5fa68e; }
.src-chip.src-mas { background: #f7e3b3; color: #5a3e0a; border: 1px solid #d4a85d; }

.gt-toggle {
  display: inline-flex; align-items: center; gap: 3px;
  color: #555; cursor: pointer; user-select: none;
  margin-left: 4px;
  & > input { margin: 0; cursor: pointer; }
}
.gt-chip {
  display: inline-block;
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 700;
  font-family: Monaco, monospace;
}
.gt-chip.gt-yes { background: #d4e8df; color: #0a4a3a; border: 1px solid #5fa68e; }
.gt-chip.gt-no  { background: #f1d6cb; color: #5a1f10; border: 1px solid #b86048; }
.gt-chip.gt-na  { background: #eee;    color: #777;   border: 1px solid #ccc; }

.restore-btn {
  font-size: 10px;
  padding: 1px 6px;
  border: 1px solid #999;
  background: #f5f5f0;
  border-radius: 2px;
  cursor: pointer;
  color: #444;
  &:hover:not(:disabled) {
    background: #ffe082;
    border-color: #d4a85d;
    color: #1a1a1a;
  }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
}
</style>
