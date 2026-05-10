<template>
  <div class="panel">
    <div class="panel-head">
      <span>V4 · Bipartite Detail</span>
      <span class="tiny muted">{{ pairsToShow.length }} pair(s) · click a person</span>
      <span class="batch-ctl tiny" v-if="pairsToShow.length">
        gap ≥
        <input class="thresh-input" type="number" step="0.1" v-model.number="batchThresh" />
        <button class="btn small" :disabled="!pairsToShow.length || batching" @click="runBatch">
          {{ batching ? '…' : 'batch' }}
        </button>
      </span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v4')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body no-pad" ref="wrapRef">
      <svg ref="svgRef" class="bp-svg"></svg>
      <div v-if="!pairsToShow.length" class="overlay muted">no selection — click a hex (V3 honeycomb) or a dot (V3 scatter)</div>
      <div v-if="batchStatus" class="batch-status tiny">{{ batchStatus }}</div>

      <!-- Profile popup overlay -->
      <div v-if="popup" class="profile-popup" @click.self="popup = null">
        <div class="popup-card">
          <div class="popup-head">
            <span class="chip">{{ popup.role === 'husband' ? 't' : 'c' }}-{{ popup.id }}</span>
            <span class="tiny muted">{{ popup.role }}</span>
            <button class="popup-close" @click="popup = null">×</button>
          </div>
          <div v-if="popup.loading" class="tiny muted">fetching profile…</div>
          <table v-else class="popup-table">
            <tr><td>sex</td><td>{{ popup.profile?.sex ?? '?' }}</td></tr>
            <tr><td>birth</td><td>{{ popup.profile?.birth_year ?? '?' }}</td></tr>
            <tr>
              <td>banner</td>
              <td>
                <template v-if="popup.profile?.banner_label">
                  {{ popup.profile.banner_label }}
                  <span class="muted">({{ popup.profile.banner_id }})</span>
                </template>
                <template v-else>—</template>
              </td>
            </tr>
            <tr>
              <td>region</td>
              <td>{{ popup.profile?.region_label ?? '—' }}</td>
            </tr>
            <tr><td>community</td><td>{{ popup.profile?.community_id ?? '?' }}</td></tr>
            <tr><td>household</td><td>{{ popup.profile?.household_id ?? '?' }}</td></tr>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, watch, onMounted, onUnmounted } from 'vue'
import * as d3 from 'd3'
import bus from '../utils/eventbus.js'
import { getProfile, overrideMatch } from '../api/client.js'

const appState = inject('appState')
const svgRef = ref(null)
const wrapRef = ref(null)
const selectedPairs = ref([])

// Batch auto-accept: groups by husband, picks argmax(score_gap) per husband,
// accepts pairs whose score_gap >= batchThresh (default 1.0 ≈ 87% precision
// per HGT calibration), then routes the first remaining husband to V5.
const batchThresh = ref(1.0)
const batching = ref(false)
const batchStatus = ref('')

// Profile popup overlay
const popup = ref(null)  // { id, role: 'husband'|'wife', loading, profile }

const pairsToShow = computed(() => selectedPairs.value || [])

function onHexSelect(payload) {
  selectedPairs.value = (payload?.pairs || []).slice()
  batchStatus.value = ''
  draw()
}
function onHexClear() {
  selectedPairs.value = []
  batchStatus.value = ''
  popup.value = null
  draw()
}
function onAccepted(evt) {
  if (!evt || evt.husband_id == null || evt.wife_id == null) return
  const before = selectedPairs.value.length
  selectedPairs.value = selectedPairs.value.filter(
    p => !(p.husband_id === evt.husband_id && p.wife_id === evt.wife_id)
  )
  if (selectedPairs.value.length !== before) draw()
}

// ──────────────────────────────────────────────────────────────────────
// Person click → husband emits person-selected (V5 picks up); wife shows
// profile popup only.
// ──────────────────────────────────────────────────────────────────────
async function onPersonClick(id, role) {
  if (role === 'husband') {
    bus.emit('person-selected', { id, role })
  }
  popup.value = { id, role, loading: true, profile: null }
  try {
    const p = await getProfile(id)
    if (popup.value && popup.value.id === id) {
      popup.value = { id, role, loading: false, profile: p }
    }
  } catch (_) {
    if (popup.value && popup.value.id === id) {
      popup.value = { id, role, loading: false, profile: null }
    }
  }
}

// ──────────────────────────────────────────────────────────────────────
// Batch auto-accept
// ──────────────────────────────────────────────────────────────────────
async function runBatch() {
  if (!pairsToShow.value.length || batching.value) return
  batching.value = true
  const thresh = Number(batchThresh.value || 0)

  // Group by husband, pick argmax(score_gap) per husband
  const byHusband = new Map()
  for (const p of pairsToShow.value) {
    const cur = byHusband.get(p.husband_id)
    if (!cur || (p.score_gap ?? -Infinity) > (cur.score_gap ?? -Infinity)) {
      byHusband.set(p.husband_id, p)
    }
  }
  const husbandsTotal = byHusband.size
  const acceptedKeys = new Set()
  let acceptedN = 0

  for (const top of byHusband.values()) {
    if ((top.score_gap ?? -Infinity) < thresh) continue
    acceptedKeys.add(`${top.husband_id}|${top.wife_id}`)
    acceptedN += 1
    bus.emit('match-accepted', {
      husband_id: top.husband_id, wife_id: top.wife_id, score: top.score, source: 'v4-batch',
    })
    try {
      await overrideMatch(
        top.husband_id, top.wife_id, top.score ?? 0, 'v4-batch',
        appState.year, appState.ablation,
      )
    } catch (_) { /* offline-safe */ }
  }

  // Remove accepted pairs ONLY (other husbands' candidates remain visible).
  selectedPairs.value = pairsToShow.value.filter(
    p => !acceptedKeys.has(`${p.husband_id}|${p.wife_id}`)
  )

  // Route the first remaining husband to V5 for MAS negotiation.
  const remainingHusbands = Array.from(new Set(selectedPairs.value.map(p => p.husband_id)))
  if (remainingHusbands.length) {
    bus.emit('person-selected', { id: remainingHusbands[0], role: 'husband' })
  }

  batchStatus.value =
    `auto-accepted ${acceptedN} / ${husbandsTotal} (gap ≥ ${thresh.toFixed(1)})`
    + (remainingHusbands.length ? ` · ${remainingHusbands.length} husband(s) → V5 (first loaded)` : '')
  batching.value = false
  draw()
}

// ──────────────────────────────────────────────────────────────────────
// Render
// ──────────────────────────────────────────────────────────────────────
function draw() {
  if (!svgRef.value || !wrapRef.value) return
  const r = wrapRef.value.getBoundingClientRect()
  const W = r.width, H = r.height
  if (!W || !H) return
  const svg = d3.select(svgRef.value).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()
  const pairs = pairsToShow.value
  if (!pairs.length) return

  const husbands = Array.from(new Set(pairs.map(p => p.husband_id)))
  const wives = Array.from(new Set(pairs.map(p => p.wife_id)))
  const pad = { l: 90, r: 90, t: 24, b: 16 }
  const yH = d3.scalePoint().domain(husbands).range([pad.t, H - pad.b]).padding(0.4)
  const yW = d3.scalePoint().domain(wives).range([pad.t, H - pad.b]).padding(0.4)
  const xH = pad.l, xW = W - pad.r

  // Edges (drawn first so nodes + score labels render on top)
  const edgeG = svg.append('g').attr('class', 'edges')
  edgeG.selectAll('path').data(pairs).enter().append('path')
    .attr('d', d => {
      const a = [xH, yH(d.husband_id)], b = [xW, yW(d.wife_id)]
      const mx = (a[0] + b[0]) / 2
      return `M${a[0]},${a[1]} C${mx},${a[1]} ${mx},${b[1]} ${b[0]},${b[1]}`
    })
    .attr('fill', 'none')
    .attr('stroke', d =>
      d.hungarian_correct === true ? '#0f6e56'
      : d.hungarian_correct === false ? '#993c1d'
      : '#888780')
    .attr('stroke-opacity', 0.6)
    .attr('stroke-width', d => 0.6 + 1.6 * Math.min(1, Math.max(0, d.score / 6)))

  // Edge HGT score labels at the bezier midpoint with rounded rect bg
  const labelG = svg.append('g').attr('class', 'edge-labels')
  for (const d of pairs) {
    const mx = (xH + xW) / 2
    const my = (yH(d.husband_id) + yW(d.wife_id)) / 2
    const txt = (d.score ?? 0).toFixed(2)
    const w = 6 + txt.length * 5.4
    const g = labelG.append('g').attr('transform', `translate(${mx},${my})`)
    g.append('rect')
      .attr('x', -w / 2).attr('y', -7.5)
      .attr('width', w).attr('height', 14)
      .attr('rx', 3)
      .attr('fill', '#fff').attr('stroke', '#bbb').attr('stroke-width', 0.6)
      .attr('opacity', 0.92)
    g.append('text')
      .attr('text-anchor', 'middle').attr('dy', 3.5)
      .style('font-size', '9px').style('font-family', 'Monaco, monospace')
      .style('fill', d.hungarian_correct === true ? '#0a4a3a'
                    : d.hungarian_correct === false ? '#7a2a13' : '#444')
      .text(txt)
  }

  // Husband nodes (clickable → V5)
  svg.append('g').selectAll('g.h').data(husbands).enter().append('g').attr('class', 'h')
    .each(function (id) {
      const g = d3.select(this)
      g.attr('transform', `translate(${xH},${yH(id)})`)
        .style('cursor', 'pointer')
        .on('click', () => onPersonClick(id, 'husband'))
      g.append('circle').attr('r', 6).attr('fill', '#1d9e75').attr('stroke', '#1a1a1a').attr('stroke-width', 0.7)
      g.append('text').attr('x', -10).attr('y', 4).attr('text-anchor', 'end')
        .style('font-size', '10px').style('cursor', 'pointer').text(id)
    })

  // Wife nodes (clickable → popup)
  svg.append('g').selectAll('g.w').data(wives).enter().append('g').attr('class', 'w')
    .each(function (id) {
      const g = d3.select(this)
      g.attr('transform', `translate(${xW},${yW(id)})`)
        .style('cursor', 'pointer')
        .on('click', () => onPersonClick(id, 'wife'))
      g.append('circle').attr('r', 6).attr('fill', '#ba7517').attr('stroke', '#1a1a1a').attr('stroke-width', 0.7)
      g.append('text').attr('x', 10).attr('y', 4).attr('text-anchor', 'start')
        .style('font-size', '10px').style('cursor', 'pointer').text(id)
    })

  // Title
  svg.append('text').attr('x', W / 2).attr('y', 14).attr('text-anchor', 'middle')
    .style('font-size', '10px').style('fill', '#666')
    .text(`${husbands.length} husbands × ${wives.length} wives · ${pairs.length} pair edges`)
}

watch(() => `${appState.year}|${appState.ablation}`, () => {
  selectedPairs.value = []
  batchStatus.value = ''
  popup.value = null
  draw()
})

onMounted(() => {
  bus.on('hex-select', onHexSelect)
  bus.on('hex-clear', onHexClear)
  bus.on('match-accepted', onAccepted)
  window.addEventListener('resize', draw)
  draw()
})
onUnmounted(() => {
  bus.off('hex-select', onHexSelect)
  bus.off('hex-clear', onHexClear)
  bus.off('match-accepted', onAccepted)
  window.removeEventListener('resize', draw)
})
</script>

<style lang="less" scoped>
.bp-svg { width: 100%; height: 100%; display: block; }
.panel-body { position: relative; }
.overlay { position: absolute; inset: 0; display: grid; place-items: center; font-size: 11px; }

.batch-ctl {
  display: inline-flex; align-items: center; gap: 4px;
  margin-left: 6px; color: #555;
  .thresh-input {
    width: 38px; font-size: 10px; padding: 1px 3px;
    border: 1px solid #888; border-radius: 3px; background: #f5f5f5;
  }
  .btn.small {
    font-size: 10px; padding: 1px 7px;
    border: 1px solid #888; border-radius: 3px;
    background: #f5f5f5; cursor: pointer; color: #1a1a1a;
    &:hover:not(:disabled) { background: #ffe082; border-color: #d4a85d; }
    &:disabled { opacity: 0.4; cursor: not-allowed; }
  }
}

.batch-status {
  position: absolute; top: 4px; left: 8px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #d4a85d; border-radius: 3px;
  padding: 2px 6px; color: #5a4a2a;
  z-index: 5; pointer-events: none;
}

.profile-popup {
  position: absolute; inset: 0;
  background: rgba(0, 0, 0, 0.18);
  display: grid; place-items: center;
  z-index: 10;
}
.popup-card {
  background: #fff; border: 1px solid #888; border-radius: 4px;
  min-width: 220px; padding: 8px 10px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
}
.popup-head {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #eee;
  .chip {
    font-size: 10px; padding: 1px 6px; border-radius: 3px;
    background: #f0efe9; font-family: Monaco, monospace;
  }
}
.popup-close {
  margin-left: auto; background: transparent; border: none; cursor: pointer;
  font-size: 16px; color: #666; padding: 0 4px;
  &:hover { color: #1a1a1a; }
}
.popup-table {
  font-size: 11px; width: 100%; border-collapse: collapse;
  td { padding: 1px 4px; }
  td:first-child { color: #888; width: 80px; }
  td:last-child { font-family: Monaco, monospace; }
}
</style>
