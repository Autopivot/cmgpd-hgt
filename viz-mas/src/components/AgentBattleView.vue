<template>
  <div class="panel battle">
    <div class="panel-head">
      <span>V5: MAS View</span>
      <span class="actions">
        <span class="tiny muted" v-if="husband">t-{{ husband.id }}</span>
        <span v-if="currentRound > 0" class="round-chip tiny" :class="{ paused: isPaused }">
          R{{ currentRound }}/6 · {{ currentRoundLabel }}
        </span>
        <button v-if="isPaused && currentRound < 6"
          class="btn primary"
          :disabled="advancing"
          @click="approveAndAdvance">
          {{ advancing ? '…' : 'Approve & Advance →' }}
        </button>
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

      <!-- Husband life-history (DS0003 events + income) -->
      <div v-if="husband && (husbandNarrative || husbandPersona)" class="row narrative-row">
        <div class="narrative-head" @click="narrativeOpen = !narrativeOpen">
          <span class="caret">{{ narrativeOpen ? '▾' : '▸' }}</span>
          <span class="tiny muted">life history · t-{{ husband.id }}</span>
          <span v-if="husbandNarrative?.birth_year" class="tiny muted">
            b{{ husbandNarrative.birth_year }} → {{ appState.year }}
          </span>
          <span v-if="husbandNarrative" class="tiny muted">
            · {{ husbandNarrative.events?.length || 0 }} events · {{ husbandNarrative.income?.length || 0 }} income years
          </span>
        </div>
        <div v-show="narrativeOpen" class="narrative-body">
          <div v-if="husbandPersona" class="persona-block">
            <div class="persona-headline">{{ husbandPersona.headline }}</div>
            <div v-if="husbandPersona.traits?.length" class="chip-row">
              <span v-for="t in husbandPersona.traits" :key="'t-'+t" class="trait-chip">{{ t }}</span>
            </div>
            <div v-if="husbandPersona.values?.length" class="chip-row">
              <span class="lbl">values:</span>
              <span v-for="v in husbandPersona.values" :key="'v-'+v" class="value-chip">{{ v }}</span>
            </div>
            <div v-if="husbandPersona.red_flags?.length" class="chip-row">
              <span class="lbl">⚠</span>
              <span v-for="r in husbandPersona.red_flags" :key="'r-'+r" class="flag-chip">{{ r }}</span>
            </div>
            <div v-if="husbandPersona.motifs?.length" class="chip-row">
              <span class="lbl">motifs:</span>
              <span v-for="m in husbandPersona.motifs" :key="'m-'+m"
                    class="motif-chip" :title="MOTIF_LABELS[m] || m">
                {{ MOTIF_LABELS[m] || m }}
              </span>
            </div>
          </div>
          <div v-if="husbandNarrative?.events?.length" class="event-strip">
            <span v-for="ev in husbandNarrative.events" :key="ev.year + (ev.event_1 || '') + (ev.event_2 || '')"
              class="event-pill" :title="`${ev.year} · ${[ev.event_1, ev.event_2].filter(Boolean).join(' / ')}`">
              {{ ev.year }} {{ ev.event_1 || ev.event_2 }}
            </span>
          </div>
          <div v-if="husbandNarrative?.income?.length" class="income-strip">
            <span class="tiny muted">income:</span>
            <span v-for="row in husbandNarrative.income" :key="'inc-'+row.year"
              class="income-pip" :class="'lvl-'+row.level"
              :title="`${row.year} · ${row.income} (${row.level})`"></span>
          </div>
        </div>
      </div>

      <!-- Hint console -->
      <div class="row hint-row">
        <div class="hint-head">
          <span class="tiny muted">
            hint console · use <code>@everyone</code>, <code>@target</code>, or <code>@c-{wife_id}</code> · verbs:
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
        <!-- Directives applied by the natural-language router. Populated by
             nlpParseHint() — empty when only formal `@target: verb` hints
             have been used. -->
        <div v-if="directives.length" class="directives-panel">
          <div class="tiny muted" style="padding:2px 6px">applied directives</div>
          <ul class="directives-list">
            <li v-for="(d, i) in directives" :key="i" class="directive-row tiny">
              <span class="t muted">{{ d.ts }}</span>
              <span class="m"><b>{{ d.action }}</b>
                <span v-if="d.target"> · {{ d.target }}</span>
                <span class="muted"> — {{ d.summary }}</span>
              </span>
            </li>
          </ul>
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
          <CandidateCard
            v-for="a in agents"
            :key="a.id"
            :agent="a"
            :is-picked="!!(accepted && accepted.id === a.id)"
            @accept="acceptOne($event)"
            @eliminate="eliminate($event)"
            @boost="boost($event, +0.5)"
            @penalise="boost($event, -0.5)"
          />
        </div>
      </div>

      <!-- Final ranking footer -->
      <div v-if="finalRanking" class="row footer-row">
        <div class="tiny muted">
          final ranking · score = (s + t)/2 − λ·|s − t| · top {{ Math.min(3, finalRanking.length) }}:
        </div>
        <ol class="rank-list tiny">
          <li v-for="(r, idx) in finalRanking.slice(0, 3)" :key="r.candidate_id"
              :class="{ winner: idx === 0 }">
            <span class="chip c">c-{{ r.candidate_id }}</span>
            <span class="final-num">final {{ r.final_score?.toFixed(2) }}</span>
            <span class="muted">
              = ({{ r.target_score?.toFixed(1) ?? '—' }} + {{ r.candidate_score?.toFixed(1) ?? '—' }})/2
              − {{ (r.lambda ?? 0.3).toFixed(2) }}·|{{ r.target_score?.toFixed(1) ?? '—' }}−{{ r.candidate_score?.toFixed(1) ?? '—' }}|
            </span>
            <button v-if="idx === 0 && !accepted" class="btn primary tiny"
                    @click="acceptRanked(r)">Accept this match</button>
            <span v-else-if="idx === 0 && accepted" class="tiny ok">✓ accepted</span>
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
  advanceRound, getNarrative, nlpParseHint,
} from '../api/client.js'
import bus from '../utils/eventbus.js'
import CandidateCard from './CandidateCard.vue'

// SEAL motif IDs (subset emitted by the persona frame). Keep in sync with
// the exemplar table in client.js (`RULE_DEFAULTS.motifs`).
const MOTIF_LABELS = {
  m1_father_brother: 'Father → brother → wife',
  m2_uncle_in_law:   'Uncle ↔ in-law',
  m3_same_household: 'Same household',
  m4_banner_endog:   'Banner endogamy',
}

const appState = inject('appState')
const husband = ref(null)        // { id, ... }
const husbandProfile = ref(null) // { sex, birth_year, banner_id, ... } from "stage:profile"
const candidates = ref([])       // raw candidates from "stage:filter"
const agents = ref([])           // per-candidate cards (mirrors candidates + LLM scores)
const finalRanking = ref(null)
const accepted = ref(null)
// Structured directives surfaced by the natural-language hint router. Each
// entry is { action, target, params, raw } and is appended on every
// successful /api/hint/parse fallback. Rendered in the V5 console so the
// user can see what their freeform text actually got translated into.
const directives = ref([])
const running = ref(false)
const streamState = ref('idle')
const systemLog = ref([])
const logRef = ref(null)
const hint = ref('')
const verbs = ['boost', 'penalise', 'eliminate', 'accept']

// 6-round bilateral negotiation state.
//   currentRound 0   = pre-arena
//   currentRound 1-6 = active round
//   isPaused === true after a `round_paused` frame; cleared when user advances
const currentRound = ref(0)
const currentRoundLabel = ref('')
const isPaused = ref(false)
const advancing = ref(false)
const husbandNarrative = ref(null)   // { events, income, birth_year } or null
const husbandPersona = ref(null)     // { headline, traits, values, red_flags } or null
const narrativeOpen = ref(true)      // collapsible panel state

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

// V4 (BipartiteDetailView) and V2 (ProcessedPairsView) emit `person-selected`
// when the user clicks a husband node. Route directly into loadHusband so V5
// populates without requiring a V3 hex click first.
function onPersonSelected(payload) {
  if (payload?.role !== 'husband') return
  if (payload?.id == null) {
    // V4 cleared its husband — drop V5 state too so the panel doesn't sit
    // on the previous person while V4 / V6 have already moved on.
    closeWS()
    husband.value = null
    husbandProfile.value = null
    candidates.value = []
    agents.value = []
    finalRanking.value = null
    accepted.value = null
    directives.value = []
    streamState.value = 'idle'
    currentRound.value = 0
    currentRoundLabel.value = ''
    isPaused.value = false
    husbandNarrative.value = null
    husbandPersona.value = null
    return
  }
  loadHusband(payload.id)
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
  currentRound.value = 0
  currentRoundLabel.value = ''
  isPaused.value = false
  husbandNarrative.value = null
  husbandPersona.value = null
  // Pre-fetch the husband's life history for the narrative panel — even
  // before the arena spins up, the user can preview events + income.
  const year = appState.year
  try {
    const n = await getNarrative(id, year)
    if (n && (n.events?.length || n.income?.length)) husbandNarrative.value = n
  } catch (_) { /* offline-safe */ }
  // V5 → V6 contract: husband loaded, no candidates yet (▶ arena not pressed).
  bus.emit('cohort-context', { husband_id: id, candidate_ids: [] })
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
  currentRound.value = 0
  currentRoundLabel.value = ''
  isPaused.value = false
  husbandPersona.value = null
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
  // V5 → V6 contract: clear cohort context for downstream views.
  bus.emit('cohort-context', { husband_id: null, candidate_ids: [] })
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
        // V5 → V6 contract: candidates populated.
        bus.emit('cohort-context', {
          husband_id: husband.value?.id ?? null,
          candidate_ids: agents.value.map(a => a.id),
        })
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
    // ── 6-round bilateral negotiation frames ──────────────────────────
    case 'round_start':
      currentRound.value = e.round
      currentRoundLabel.value = e.label || ''
      isPaused.value = false
      logSys(`<b>round ${e.round}</b> · ${e.label}`)
      break
    case 'narrative': {
      // Husband's narrative goes to the top panel; candidates' narratives
      // attach to their cards so CandidateCard can expose them on demand.
      const isHusband = husband.value && (e.person_id === husband.value.id || e.person_id === `P${husband.value.id}`)
      if (isHusband) husbandNarrative.value = { events: e.events || [], income: e.income || [], birth_year: e.birth_year ?? null }
      else {
        const a = agents.value.find(a => a.id === e.person_id || `c-${a.id}` === e.person_id)
        if (a) a.narrative = { events: e.events || [], income: e.income || [], birth_year: e.birth_year ?? null }
      }
      break
    }
    case 'persona': {
      const isHusband = husband.value && (e.person_id === husband.value.id || e.person_id === `P${husband.value.id}`)
      if (isHusband) husbandPersona.value = e.resume
      else {
        const a = agents.value.find(a => a.id === e.person_id || `c-${a.id}` === e.person_id)
        if (a) a.persona = e.resume
      }
      break
    }
    case 'query':
    case 'answer': {
      // Route to whichever candidate is on the non-target side of this exchange.
      const cid = e.from === 'target' ? e.to : e.from
      const candId = String(cid).startsWith('c-') ? String(cid).slice(2) : cid
      const a = agents.value.find(a => a.id === candId)
      if (a) {
        if (!Array.isArray(a.conversation)) a.conversation = []
        a.conversation.push({ round: currentRound.value, kind: e.type, from: e.from, to: e.to, text: e.text, ts: Date.now() })
      }
      break
    }
    case 'round_scores':
      for (const p of e.pairs || []) {
        const a = agents.value.find(a => a.id === p.candidate_id)
        if (!a) continue
        a.target_score = p.target_score
        a.candidate_score = p.candidate_score
        a.target_reason = p.target_reason
        a.candidate_reason = p.candidate_reason
        if (!a.round_scores) a.round_scores = {}
        a.round_scores[e.round] = {
          target_score: p.target_score,
          candidate_score: p.candidate_score,
          target_reason: p.target_reason,
          candidate_reason: p.candidate_reason,
        }
      }
      logSys(`round ${e.round} scores: ${e.pairs?.length ?? 0} candidates`)
      break
    case 'round_paused':
      isPaused.value = true
      logSys(`round ${e.round} paused — awaiting Approve & Advance`, 'sys')
      break
    case 'final_ranking':
      finalRanking.value = e.ranking
      currentRound.value = 6
      currentRoundLabel.value = 'final'
      isPaused.value = true   // user must accept manually
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
  // Server-side role: @everyone/@all → 'all'; @target → 'target';
  // single @c-XXX → that candidate; multiple → 'all' (server broadcasts).
  let role = 'all'
  if (/@target\b/i.test(txt)) role = 'target'
  else if (ids.length === 1) role = `c-${ids[0]}`
  return { verb: verb === 'penalize' ? 'penalise' : verb, ids: [...new Set(ids)], role }
}

async function approveAndAdvance() {
  if (!husband.value || !isPaused.value || advancing.value) return
  advancing.value = true
  try {
    await advanceRound(husband.value.id)
    isPaused.value = false
  } catch (e) {
    logSys(`advance failed: ${e.message || e}`, 'err')
  } finally {
    advancing.value = false
  }
}

// Compose a short human-readable summary of an NLP-router action, e.g.
//   { action: 'eliminate', target: 'c-P165718' }                 → "eliminate c-P165718"
//   { action: 'modify_persona_field',
//     target: 'c-P93553',
//     params: { field: 'banner', value: 3 } }                    → "modify banner of c-P93553 → 3"
function formatDirective(d) {
  if (!d || typeof d !== 'object') return String(d)
  const act = d.action || d.verb || 'op'
  const tgt = d.target || d.subject || ''
  const p = d.params || {}
  if (act === 'modify_persona_field' && p.field !== undefined) {
    return `modify ${p.field} of ${tgt} → ${p.value ?? ''}`
  }
  const extras = Object.keys(p).length
    ? ' ' + Object.entries(p).map(([k, v]) => `${k}=${v}`).join(' ')
    : ''
  return `${act}${tgt ? ' ' + tgt : ''}${extras}`.trim()
}

async function sendHint() {
  const text = hint.value.trim()
  if (!text || !husband.value) return
  const { verb, ids, role } = parseHint(text)
  // Local UI effects (mirror the server-side hint).
  for (const id of ids) {
    const a = agents.value.find(a => a.id === id || ('P' + a.id) === id)
    if (!a) continue
    if (verb === 'eliminate') a.eliminated = true
    else if (verb === 'accept') acceptOne(a)
    else if (verb === 'boost' && a.target_score != null) a.target_score = Math.min(10, a.target_score + 0.5)
    else if (verb === 'penalise' && a.target_score != null) a.target_score = Math.max(0, a.target_score - 0.5)
  }

  // Formal-grammar fast path: a recognised verb (boost/penalise/eliminate/
  // accept) is enough to treat the input as a structural directive and
  // send it straight to the negotiator, skipping the LLM round-trip.
  const formalMatched = verb !== ''

  if (formalMatched) {
    try { await sendNegotiationHint(husband.value.id, text, role, currentRound.value) }
    catch (e) { logSys(`hint POST failed: ${e.message || e}`, 'err') }
    hint.value = ''
    logSys(`<b>hint</b> [${role}] ${text}`)
    return
  }

  // Natural-language fallback: ask the backend router to translate the
  // freeform text into structured actions, then surface each one in the
  // chat log + directives list. On any failure, fall back to the legacy
  // raw-text hint so the negotiator still hears the user.
  logSys(`<b>hint</b> [${role}] ${text}`)
  try {
    const ctx = {
      candidate_ids: candidates.value.map(c => c.id),
      current_round: currentRound.value,
    }
    const resp = await nlpParseHint(husband.value.id, text, ctx)
    const actions = Array.isArray(resp?.actions) ? resp.actions : []
    if (actions.length === 0) {
      logSys('[router] no actions returned — forwarding as raw chat', 'sys')
      try { await sendNegotiationHint(husband.value.id, text, role, currentRound.value) }
      catch (e) { logSys(`hint POST failed: ${e.message || e}`, 'err') }
    } else {
      for (const a of actions) {
        const summary = formatDirective(a)
        logSys(`[router] ${summary}`, 'ok')
        directives.value.push({
          ts: new Date().toLocaleTimeString(),
          action: a.action || a.verb || 'op',
          target: a.target || a.subject || '',
          params: a.params || {},
          summary,
          raw: text,
        })
      }
    }
  } catch (e) {
    logSys(`[router] could not parse: ${e.message || e}`, 'err')
    // Best-effort: still forward the raw text so the negotiator gets the
    // user's intent even if the router is offline.
    try { await sendNegotiationHint(husband.value.id, text, role, currentRound.value) }
    catch (err) { logSys(`hint POST failed: ${err.message || err}`, 'err') }
  }
  hint.value = ''
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

// Accept the top-1 from the round-6 final ranking.
async function acceptRanked(r) {
  const a = agents.value.find(a => a.id === r.candidate_id) || { id: r.candidate_id, target_score: r.final_score }
  await acceptOne(a)
}

// ── Lifecycle ──────────────────────────────────────────────────────────
watch(() => `${appState.year}|${appState.ablation}`, () => {
  husband.value = null
  husbandProfile.value = null
  candidates.value = []
  agents.value = []
  finalRanking.value = null
  accepted.value = null
  directives.value = []
  // V5 → V6 contract: cohort context resets when the user changes year/ablation.
  bus.emit('cohort-context', { husband_id: null, candidate_ids: [] })
  closeWS()
})

onMounted(() => {
  bus.on('hex-select', onHexSelect)
  bus.on('person-selected', onPersonSelected)
})
onUnmounted(() => {
  bus.off('hex-select', onHexSelect)
  bus.off('person-selected', onPersonSelected)
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
.directives-panel {
  margin-top: 4px; background: #fffbe9; border: 1px solid #e3d27a;
  border-radius: 3px; max-height: 80px; overflow: auto;
}
.directives-list { list-style: none; margin: 0; padding: 2px 6px; }
.directive-row {
  display: flex; gap: 6px; padding: 1px 0;
  font-family: "Monaco", monospace; font-size: 10px;
}
.directive-row .t { flex: 0 0 auto; }
.directive-row .m { flex: 1 1 auto; }
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

// Round indicator chip in the header.
.round-chip {
  background: #d4a85d; color: #1a1a1a;
  padding: 2px 7px; border-radius: 3px;
  font-weight: 600; font-variant-numeric: tabular-nums;
  &.paused { background: #ffd84a; box-shadow: 0 0 0 2px #ffd84a44; }
}
.btn.primary {
  background: #0f6e56; color: #fff; border: 1px solid #0a4a3a;
  padding: 3px 10px; font-weight: 600; font-size: 11px;
  border-radius: 3px; cursor: pointer;
  &:hover:not(:disabled) { background: #0a4a3a; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}
.btn.primary.tiny { padding: 1px 7px; font-size: 10px; margin-left: 6px; }

// Husband narrative panel.
.narrative-row { background: #fbfaf2; }
.narrative-head {
  display: flex; align-items: center; gap: 6px;
  cursor: pointer; user-select: none;
  &:hover { color: #0a4a3a; }
  .caret { color: #888; font-size: 10px; width: 10px; }
}
.narrative-body { margin-top: 4px; display: flex; flex-direction: column; gap: 4px; }
.persona-block {
  padding: 4px 6px; background: #fff; border: 1px solid #e0d8c0; border-radius: 3px;
  .persona-headline { font-weight: 600; font-size: 11px; margin-bottom: 3px; }
}
.chip-row { display: flex; flex-wrap: wrap; gap: 3px; align-items: center; margin-top: 2px;
  .lbl { font-size: 9px; color: #888; margin-right: 2px; }
}
.trait-chip, .value-chip, .flag-chip {
  font-size: 9px; padding: 1px 5px; border-radius: 8px;
}
.trait-chip { background: #e8efe8; color: #2a4a3a; }
.value-chip { background: #f0e8d8; color: #5a4a2a; }
.flag-chip  { background: #f5d8d0; color: #8a3a1a; }
.event-strip {
  display: flex; flex-wrap: wrap; gap: 3px;
  max-height: 60px; overflow: auto;
}
.event-pill {
  font-size: 9px; padding: 1px 5px; background: #f0efe9;
  border-radius: 8px; color: #444; white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.income-strip { display: flex; align-items: center; gap: 2px; flex-wrap: wrap; }
.income-pip {
  display: inline-block; width: 6px; height: 10px; border-radius: 1px;
  &.lvl-low { background: #993c1d; }
  &.lvl-mid { background: #d4a85d; }
  &.lvl-high { background: #0f6e56; }
}

.rank-list li.winner { font-weight: 600; }
.rank-list .final-num { font-variant-numeric: tabular-nums; color: #0f6e56; }
.rank-list .ok { color: #0f6e56; margin-left: 6px; }
</style>
