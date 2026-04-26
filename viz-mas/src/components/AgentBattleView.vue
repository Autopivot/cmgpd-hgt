<template>
  <div class="panel battle">
    <div class="panel-head">
      <span>V5 · Agent Arena · MAS Negotiation</span>
      <span class="actions">
        <span class="tiny muted" v-if="husband">t-{{ husband.id }}</span>
        <span v-if="streamState" class="stream-state tiny" :class="streamState">{{ streamState }}</span>
        <button class="btn ghost" :disabled="!husband || running" @click="startBattle">▶ arena</button>
        <button class="fs-btn" @click="bus.emit('full-screen', 'v5')" title="Full screen">⛶</button>
      </span>
    </div>
    <div class="panel-body no-pad">
      <!-- Husband profile -->
      <div class="row target-row">
        <div class="target">
          <div v-if="!husband" class="muted tiny" style="padding:6px">
            click a husband in V3 (hex / scatter) or V2 to load target
          </div>
          <div v-else>
            <div class="t-header">
              <span class="chip">t-{{ husband.id }}</span>
              <span class="tiny" v-if="husbandProfile">
                sex={{ husbandProfile.sex || '—' }} · b{{ husbandProfile.birth_year ?? '?' }}
                · bnr{{ husbandProfile.banner_id ?? '?' }}
                · com{{ husbandProfile.community_id ?? '?' }}
              </span>
              <span class="tiny muted" v-else>fetching profile…</span>
            </div>
            <div class="cohort-info tiny muted">
              cohort {{ appState.year }} ({{ appState.ablation }}) ·
              {{ candidates.length }} top candidates
            </div>
          </div>
        </div>
      </div>

      <!-- Hint console -->
      <div class="row hint-row">
        <div class="hint-head">
          <span class="tiny muted">
            hint console · use <code>@c-{wife_id}</code> or <code>@all</code> · verbs:
            boost / penalise / eliminate / accept
          </span>
        </div>
        <div class="hint-log" ref="logRef">
          <div v-for="(l, i) in systemLog" :key="i" class="log-line" :class="'lvl-'+l.level">
            <span class="t">{{ l.t }}</span>
            <span class="m" v-html="l.html"></span>
          </div>
          <div v-if="!systemLog.length" class="muted tiny" style="padding:4px 6px">no messages</div>
        </div>
        <div class="hint-input">
          <span class="verbs">
            <button class="verb" v-for="v in verbs" :key="v" @click="appendVerb(v)">{{ v }}</button>
          </span>
          <input
            class="hint-field"
            v-model="hint"
            placeholder="@c-P12345 boost: same banner, +2"
            :disabled="!husband"
            @keydown.enter="sendHint"
          />
          <button class="btn" :disabled="!hint.trim() || !husband" @click="sendHint">send</button>
        </div>
      </div>

      <!-- Arena grid: one card per candidate (LLM agent per wife) -->
      <div class="row arena-row">
        <div v-if="!agents.length" class="muted tiny" style="padding:8px">
          no candidates yet — press ▶ arena to spin up the per-person agents
        </div>
        <div v-else class="arena-grid">
          <div v-for="a in agents" :key="a.id" class="arena-card"
               :class="{ dim: a.eliminated, pick: accepted && accepted.id === a.id }">
            <div class="card-head">
              <span class="chip c">c-{{ a.id }}</span>
              <span class="score" :class="scoreClass(a.target_score)">
                {{ a.target_score?.toFixed?.(1) ?? '—' }}
              </span>
              <span class="bilateral tiny" v-if="a.candidate_score != null"
                    :title="`candidate (wife) returned ${a.candidate_score.toFixed(1)}`">
                ⇄ {{ a.candidate_score?.toFixed?.(1) }}
              </span>
            </div>
            <div class="card-meta tiny" v-if="a.profile">
              b{{ a.profile.birth_year ?? '?' }} · bnr{{ a.profile.banner_id ?? '?' }} ·
              com{{ a.profile.community_id ?? '?' }}
            </div>
            <div class="card-pre tiny muted">
              HGT {{ a.pre_score?.toFixed?.(2) }} · gap {{ a.score_gap?.toFixed?.(2) }} ·
              {{ a.hgt_label === 1 ? 'GT pair' : 'hard neg' }}
            </div>
            <div class="card-feed">
              <div v-if="a.target_reason" class="reason">
                <strong>H→W:</strong> {{ a.target_reason }}
              </div>
              <div v-if="a.candidate_reason" class="reason cand">
                <strong>W→H:</strong> {{ a.candidate_reason }}
              </div>
              <div v-if="!a.target_reason && a.feed.length" class="feed-tokens">
                {{ a.feed.join('') }}
              </div>
            </div>
            <div class="card-actions">
              <button class="tiny linkbtn"
                      :disabled="a.eliminated || (accepted && accepted.id === a.id)"
                      @click="acceptOne(a)">accept</button>
              <button class="tiny linkbtn warn"
                      :disabled="a.eliminated"
                      @click="eliminate(a)">eliminate</button>
              <button class="tiny linkbtn"
                      @click="boost(a, +0.5)">boost</button>
              <button class="tiny linkbtn"
                      @click="boost(a, -0.5)">penalise</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Final ranking footer -->
      <div v-if="finalRanking" class="row footer-row">
        <div class="tiny muted">
          final ranking · top {{ Math.min(3, finalRanking.length) }}:
        </div>
        <ol class="rank-list tiny">
          <li v-for="r in finalRanking.slice(0, 3)" :key="r.candidate_id">
            <span class="chip c">c-{{ r.candidate_id }}</span>
            <span>final {{ r.final_score?.toFixed(2) }}</span>
            <span class="muted">(t{{ r.target_score }}/c{{ r.candidate_score ?? '—' }} · pre{{ r.pre_score?.toFixed(2) }})</span>
          </li>
        </ol>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import {
  startNegotiation, openNegotiationStream, sendNegotiationHint, overrideMatch, getPair,
} from '../api/client.js'
import bus from '../utils/eventbus.js'

const appState = inject('appState')
const husband = ref(null)        // { id, ... }
const husbandProfile = ref(null) // { sex, birth_year, banner_id, ... } from "stage:profile"
const candidates = ref([])       // raw candidates from "stage:filter"
const agents = ref([])           // per-candidate cards (mirrors candidates + LLM scores)
const finalRanking = ref(null)
const accepted = ref(null)
const running = ref(false)
const streamState = ref('idle')
const systemLog = ref([])
const logRef = ref(null)
const hint = ref('')
const verbs = ['boost', 'penalise', 'eliminate', 'accept']

let activeWS = null

// ── Logging (visible in the hint console) ──────────────────────────────
function logSys(html, level = 'info') {
  const t = new Date().toTimeString().slice(0, 8)
  systemLog.value.push({ t, html, level })
  if (systemLog.value.length > 60) systemLog.value.splice(0, systemLog.value.length - 60)
  nextTick(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight })
}

// ── Score class ────────────────────────────────────────────────────────
function scoreClass(s) {
  if (s == null) return 'na'
  if (s >= 7) return 'hi'
  if (s >= 5) return 'mid'
  return 'lo'
}

// ── Cell-select / pair-select bridge ───────────────────────────────────
//
// V3 emits `hex-select` with `payload.pairs[*].husband_id`. We pick the
// FIRST distinct husband as the negotiation target — multi-husband
// selections (e.g. lasso) collapse to that. The user can then click ▶
// arena to launch the per-person LLM round for him.
function onHexSelect(payload) {
  const picks = payload?.pairs || []
  if (!picks.length) return
  const husbandIds = Array.from(new Set(picks.map(p => p.husband_id).filter(Boolean)))
  if (!husbandIds.length) return
  // Pull a richer profile for the target husband.
  loadHusband(husbandIds[0])
}

async function loadHusband(id) {
  // New target → kill any in-flight stream and reset the running gate so
  // the ▶ arena button isn't stuck disabled if the previous WS died
  // before connecting.
  closeWS()
  husband.value = { id }
  husbandProfile.value = null
  candidates.value = []
  agents.value = []
  finalRanking.value = null
  accepted.value = null
  streamState.value = 'idle'
}

// ── Start the negotiation ──────────────────────────────────────────────
async function startBattle() {
  if (!husband.value) return
  closeWS()
  agents.value = []
  finalRanking.value = null
  accepted.value = null
  systemLog.value = []
  streamState.value = 'starting'
  running.value = true
  logSys(`<b>start</b> negotiate ${husband.value.id} · cohort ${appState.year} · ${appState.ablation}`)

  try {
    await startNegotiation({
      husband_id: husband.value.id,
      year: appState.year,
      ablation: appState.ablation,
      auto_commit: false,
    })
  } catch (e) {
    logSys(`POST /negotiate failed: ${e.message || e}`, 'err')
    streamState.value = 'error'
    running.value = false
    return
  }

  activeWS = openNegotiationStream(husband.value.id)
  activeWS.onopen = () => { streamState.value = 'streaming' }
  activeWS.onmessage = (ev) => {
    try { handleEvent(JSON.parse(ev.data)) }
    catch (e) { logSys(`bad ws frame: ${e}`, 'err') }
  }
  activeWS.onerror = () => { logSys('ws error', 'err'); streamState.value = 'error' }
  activeWS.onclose = () => {
    running.value = false
    if (streamState.value === 'streaming') streamState.value = 'done'
  }
}

function closeWS() {
  if (activeWS) { try { activeWS.close() } catch {} ; activeWS = null }
  // Explicit reset — don't rely on ws.onclose firing, since a WS that
  // never finishes connecting won't ever dispatch 'close'.
  running.value = false
}

// ── Event dispatch ─────────────────────────────────────────────────────
function handleEvent(e) {
  switch (e.type) {
    case 'start':
      logSys(`server picked up <b>${e.husband_id}</b>`); break
    case 'stage':
      if (e.stage === 'profile') {
        husbandProfile.value = e.profile
        logSys(`profile: sex=${e.profile.sex} · banner ${e.profile.banner_id}`)
      } else if (e.stage === 'filter') {
        candidates.value = e.candidates
        // Seed the agent grid from the candidate list (target_score arrives next).
        agents.value = e.candidates.map(c => ({
          id: c.person.id,
          profile: c.person,
          pre_score: c.pre_score,
          score_gap: c.score_gap,
          hgt_label: c.hgt_label,
          target_score: null,
          target_reason: '',
          candidate_score: null,
          candidate_reason: '',
          feed: [],
          eliminated: false,
        }))
        logSys(`filter: kept ${e.candidates.length}/${e.funnel.in_cohort}`)
      }
      break
    case 'agent_prompt':
      logSys(`<i>prompt</i> ${e.side} <b>${e.person_id}</b>`, 'sys')
      break
    case 'agent_token':
      // Append streamed tokens to the corresponding agent's feed.
      if (e.side === 'target') {
        // Target = husband; route tokens to ALL candidate cards (the LLM is
        // emitting one big response that scores every candidate). Append
        // to a shared feed buffer for the husband for now.
        for (const a of agents.value) {
          if (a.feed.length < 200) a.feed.push(e.delta)
        }
      } else if (e.side === 'candidate') {
        const a = agents.value.find(a => a.id === e.person_id)
        if (a && a.feed.length < 200) a.feed.push(e.delta)
      }
      break
    case 'target_scores':
      for (const ts of e.scores) {
        const a = agents.value.find(a => a.id === ts.candidate_id)
        if (a) {
          a.target_score = ts.score
          a.target_reason = ts.reason
          a.feed = []   // reasons supersede streamed tokens
        }
      }
      logSys(`target scored ${e.scores.length} candidates`)
      break
    case 'bilateral_scores':
      for (const [cid, bs] of Object.entries(e.scores)) {
        const a = agents.value.find(a => a.id === cid)
        if (a) {
          a.candidate_score = bs.score
          a.candidate_reason = bs.reason
        }
      }
      logSys(`bilateral: ${Object.keys(e.scores).length} candidates returned a score`)
      break
    case 'final_ranking':
      finalRanking.value = e.ranking
      if (e.chosen) {
        accepted.value = { id: e.chosen.candidate_id, score: e.chosen.final_score }
        logSys(`auto-pick → <b>c-${e.chosen.candidate_id}</b> @ ${e.chosen.final_score.toFixed(2)}`, 'ok')
        bus.emit('match-accepted', { husband_id: husband.value.id, wife_id: e.chosen.candidate_id, score: e.chosen.final_score })
      } else {
        logSys('no auto-accept; pick a candidate manually')
      }
      break
    case 'committed':
      accepted.value = { id: e.match.wife_id, score: e.match.score }
      logSys(`committed → <b>c-${e.match.wife_id}</b>`, 'ok')
      bus.emit('match-accepted', { husband_id: husband.value.id, wife_id: e.match.wife_id, score: e.match.score })
      break
    case 'hint_ack':
      logSys(`hint accepted (role=${e.role}): ${e.text}`)
      break
    case 'error':
      logSys(`server error: ${e.error}`, 'err')
      break
    case 'done':
      streamState.value = 'done'
      logSys('stream done')
      break
  }
}

// ── Hint console ───────────────────────────────────────────────────────
function appendVerb(v) {
  if (hint.value && !hint.value.endsWith(' ')) hint.value += ' '
  hint.value += v + ' '
}

function parseHint(txt) {
  const ids = []
  const re = /@c-([A-Za-z0-9_]+)/g
  let m
  while ((m = re.exec(txt))) ids.push(m[1])
  const verb = (txt.match(/\b(boost|penalise|penalize|eliminate|accept)\b/i)?.[1] || '').toLowerCase()
  return { verb: verb === 'penalize' ? 'penalise' : verb, ids: [...new Set(ids)] }
}

async function sendHint() {
  const text = hint.value.trim()
  if (!text || !husband.value) return
  const { verb, ids } = parseHint(text)
  // Local UI effects (mirror the server-side hint).
  for (const id of ids) {
    const a = agents.value.find(a => a.id === id || ('P' + a.id) === id)
    if (!a) continue
    if (verb === 'eliminate') a.eliminated = true
    else if (verb === 'accept') acceptOne(a)
    else if (verb === 'boost' && a.target_score != null) a.target_score = Math.min(10, a.target_score + 0.5)
    else if (verb === 'penalise' && a.target_score != null) a.target_score = Math.max(0, a.target_score - 0.5)
  }
  try { await sendNegotiationHint(husband.value.id, text, 'all') }
  catch (e) { logSys(`hint POST failed: ${e.message || e}`, 'err') }
  hint.value = ''
  logSys(`<b>hint</b> ${text}`)
}

function boost(a, delta) {
  if (a.target_score == null) return
  a.target_score = Math.max(0, Math.min(10, a.target_score + delta))
  logSys(`local ${delta >= 0 ? 'boost' : 'penalise'} c-${a.id} (${delta > 0 ? '+' : ''}${delta})`)
}

function eliminate(a) {
  a.eliminated = true
  logSys(`local eliminate c-${a.id}`)
}

async function acceptOne(a) {
  if (!husband.value) return
  accepted.value = { id: a.id, score: a.target_score ?? 0.75 }
  logSys(`<b>accept</b> c-${a.id}`, 'ok')
  bus.emit('match-accepted', {
    husband_id: husband.value.id, wife_id: a.id, score: a.target_score,
  })
  try {
    await overrideMatch(
      husband.value.id, a.id, a.target_score ?? 0.75, 'user-accept',
      appState.year, appState.ablation,
    )
  } catch (e) { logSys(`override POST failed: ${e.message || e}`, 'err') }
}

// ── Lifecycle ──────────────────────────────────────────────────────────
watch(() => `${appState.year}|${appState.ablation}`, () => {
  husband.value = null
  husbandProfile.value = null
  candidates.value = []
  agents.value = []
  finalRanking.value = null
  accepted.value = null
  closeWS()
})

onMounted(() => bus.on('hex-select', onHexSelect))
onUnmounted(() => {
  bus.off('hex-select', onHexSelect)
  closeWS()
})
</script>

<style lang="less" scoped>
.battle .panel-body { display: flex; flex-direction: column; }
.row { padding: 6px 8px; border-bottom: 1px solid #eee; }
.row:last-child { border-bottom: none; }

.target-row .t-header { display: flex; align-items: center; gap: 6px; }
.cohort-info { margin-top: 2px; }

.hint-row { background: #fafaf5; }
.hint-head { font-size: 10px; color: #666; margin-bottom: 4px; }
.hint-log {
  background: #fff; border: 1px solid #ddd; border-radius: 3px;
  height: 60px; overflow: auto;
  font-size: 10px; font-family: "Monaco", monospace;
}
.log-line { padding: 1px 6px; }
.log-line .t { color: #888; margin-right: 6px; }
.log-line.lvl-err .m { color: #a40000; }
.log-line.lvl-ok .m { color: #0f6e56; }
.log-line.lvl-sys .m { color: #555; font-style: italic; }
.hint-input {
  display: flex; align-items: center; gap: 4px; margin-top: 4px;
  flex-wrap: wrap;
}
.hint-input .hint-field {
  flex: 1 1 200px; min-width: 0;
  font-family: "Monaco", monospace; font-size: 11px;
  padding: 3px 6px; border: 1px solid #999; border-radius: 3px;
}
.verbs { display: inline-flex; gap: 2px; }
.verb {
  font-size: 9px; padding: 1px 5px; border: 1px solid #ccc;
  background: #fafafa; cursor: pointer; border-radius: 2px;
  &:hover { background: #ffe082; border-color: #d4a85d; }
}

.arena-row { flex: 1; min-height: 0; overflow: auto; }
.arena-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 6px;
}
.arena-card {
  background: #fff; border: 1px solid #ddd; border-radius: 4px;
  padding: 5px 6px; font-size: 11px;
  display: flex; flex-direction: column; gap: 3px;
  &.dim { opacity: 0.4; }
  &.pick { border-color: #0f6e56; box-shadow: 0 0 0 2px #0f6e5644; }
}
.card-head { display: flex; align-items: center; gap: 5px; }
.card-head .score {
  font-weight: 700; font-variant-numeric: tabular-nums;
  padding: 1px 5px; border-radius: 2px;
  &.hi { background: #0f6e56; color: #fff; }
  &.mid { background: #d4a85d; color: #1a1a1a; }
  &.lo { background: #993c1d; color: #fff; }
  &.na { color: #999; }
}
.bilateral { color: #555; margin-left: auto; }
.card-meta, .card-pre { color: #666; }
.card-feed {
  font-size: 10px; color: #444;
  background: #fafaf5; border-radius: 2px;
  padding: 3px 5px; min-height: 18px; max-height: 78px; overflow: auto;
  font-family: "Monaco", monospace;
}
.card-feed .reason { margin-bottom: 2px; }
.card-feed .reason.cand { color: #0a4a3a; }
.card-feed .feed-tokens { color: #888; font-style: italic; }
.card-actions {
  display: flex; gap: 3px; margin-top: 2px;
  .linkbtn {
    background: transparent; border: 1px solid #bbb; border-radius: 2px;
    padding: 1px 5px; font-size: 9px; cursor: pointer;
    &:hover { background: #ffe082; border-color: #d4a85d; }
    &.warn { color: #993c1d; }
    &:disabled { opacity: 0.4; cursor: not-allowed; }
  }
}

.footer-row { background: #f5f5f0; }
.rank-list { padding-left: 16px; }
.rank-list li { margin: 1px 0; display: flex; align-items: center; gap: 6px; }

.stream-state {
  margin-left: auto; padding: 1px 6px; border-radius: 2px;
  background: #f0efe9; color: #555;
  &.starting { background: #fff7d6; color: #555; }
  &.streaming { background: #d4a85d; color: #1a1a1a; }
  &.done { background: #0f6e56; color: #fff; }
  &.error { background: #993c1d; color: #fff; }
}

code { background: #eee; padding: 0 3px; border-radius: 2px; font-family: "Monaco", monospace; }
.actions { display: flex; align-items: center; gap: 6px; flex: 1 1 auto; justify-content: flex-end; }
</style>
