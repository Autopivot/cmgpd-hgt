<template>
  <div class="arena-card"
       :class="{ dim: agent.eliminated, pick: isPicked }">
    <!-- Header -->
    <div class="card-head">
      <span class="chip c">c-{{ agent.id }}</span>
      <span class="score" :class="scoreClass(agent.target_score)">
        {{ formatScore(agent.target_score) }}
      </span>
      <span class="bilateral tiny" v-if="agent.candidate_score != null"
            :title="`candidate (wife) returned ${agent.candidate_score.toFixed(1)}`">
        ⇄ {{ formatScore(agent.candidate_score) }}
      </span>
    </div>

    <!-- Metadata -->
    <div class="card-meta tiny" v-if="agent.profile">
      b{{ agent.profile.birth_year ?? '?' }} · bnr{{ agent.profile.banner_id ?? '?' }} ·
      com{{ agent.profile.community_id ?? '?' }}
    </div>
    <div class="card-pre tiny muted">
      HGT {{ agent.pre_score?.toFixed?.(2) ?? '—' }}
      <template v-if="agent.score_gap != null"> · gap {{ agent.score_gap.toFixed(2) }}</template>
      <template v-if="agent.hgt_label != null"> · {{ agent.hgt_label === 1 ? 'GT pair' : 'hard neg' }}</template>
    </div>

    <!-- Streaming feed / reasons -->
    <div class="card-feed">
      <div v-if="agent.target_reason" class="reason">
        <strong>H&rarr;W:</strong> {{ agent.target_reason }}
      </div>
      <div v-if="agent.candidate_reason" class="reason cand">
        <strong>W&rarr;H:</strong> {{ agent.candidate_reason }}
      </div>
      <div v-if="!agent.target_reason && feedLength" class="feed-tokens">
        {{ feedText }}
      </div>
    </div>

    <!-- Persona summary -->
    <div v-if="agent.persona" class="persona">
      <div class="persona-headline" v-if="agent.persona.headline">
        <strong>{{ agent.persona.headline }}</strong>
      </div>
      <div class="persona-traits" v-if="personaTraits.length">
        <span v-for="(t, i) in personaTraits.slice(0, 4)" :key="i" class="trait-chip">{{ t }}</span>
      </div>
      <button class="tiny linkbtn persona-toggle" @click="personaOpen = !personaOpen">
        {{ personaOpen ? '▾' : '▸' }} persona
      </button>
      <pre v-if="personaOpen" class="persona-full">{{ personaJson }}</pre>
    </div>

    <!-- Round-score history strip -->
    <div v-if="roundScoreEntries.length" class="round-strip tiny">
      <span v-for="(rs, i) in roundScoreEntries" :key="rs.round" class="round-pip"
            :title="roundTitle(rs)">
        <span class="rp-label">R{{ rs.round }}</span>
        <span class="rp-vals">t{{ formatPip(rs.target_score) }}/c{{ formatPip(rs.candidate_score) }}</span>
        <span v-if="i < roundScoreEntries.length - 1" class="rp-sep">→</span>
      </span>
    </div>

    <!-- Actions -->
    <div class="card-actions">
      <button class="tiny linkbtn"
              :disabled="agent.eliminated || isPicked"
              @click="$emit('accept', agent)">accept</button>
      <button class="tiny linkbtn warn"
              :disabled="agent.eliminated"
              @click="$emit('eliminate', agent)">eliminate</button>
      <button class="tiny linkbtn"
              @click="$emit('boost', agent)">boost</button>
      <button class="tiny linkbtn"
              @click="$emit('penalise', agent)">penalise</button>
      <button class="tiny linkbtn convo-toggle"
              @click="convoOpen = !convoOpen"
              :title="convoOpen ? 'collapse conversation' : 'expand conversation'">
        {{ convoOpen ? '▼' : '▶' }} conversation ({{ conversation.length }})
      </button>
    </div>

    <!-- Conversation expander -->
    <div v-if="convoOpen" class="convo-panel" ref="convoPanel">
      <div v-if="!conversation.length" class="muted tiny convo-empty">
        no conversation yet — round queries and answers will appear here
      </div>
      <div v-for="(entry, idx) in conversation" :key="idx" class="convo-entry"
           :class="entryClass(entry)">
        <div class="convo-meta tiny">
          <span class="rnd">R{{ entry.round }}</span>
          <span class="kind" :class="entry.kind">{{ entry.kind }}</span>
          <span class="from-to">
            <span :class="authorClass(entry.from)">{{ authorLabel(entry.from) }}</span>
            <span class="arrow">→</span>
            <span :class="authorClass(entry.to)">{{ authorLabel(entry.to) }}</span>
          </span>
        </div>
        <div class="convo-text">{{ entry.text }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'

const props = defineProps({
  agent: { type: Object, required: true },
  isPicked: { type: Boolean, default: false },
})

defineEmits(['accept', 'eliminate', 'penalise', 'boost'])

const convoOpen = ref(false)
const personaOpen = ref(false)
const convoPanel = ref(null)

// Fallback: agent.conversation may be undefined if unit 5 hasn't merged.
const conversation = computed(() => Array.isArray(props.agent.conversation) ? props.agent.conversation : [])

const feedLength = computed(() => Array.isArray(props.agent.feed) ? props.agent.feed.length : 0)
const feedText = computed(() => Array.isArray(props.agent.feed) ? props.agent.feed.join('') : '')

const personaTraits = computed(() => {
  const p = props.agent.persona
  if (!p || !Array.isArray(p.traits)) return []
  return p.traits
})

const personaJson = computed(() => {
  try { return JSON.stringify(props.agent.persona, null, 2) }
  catch { return '' }
})

const roundScoreEntries = computed(() => {
  const rs = props.agent.round_scores
  if (!rs || typeof rs !== 'object') return []
  return Object.keys(rs)
    .map(k => ({ round: Number(k), ...(rs[k] || {}) }))
    .filter(e => Number.isFinite(e.round))
    .sort((a, b) => a.round - b.round)
})

function scoreClass(s) {
  if (s == null) return 'na'
  if (s >= 7) return 'hi'
  if (s >= 5) return 'mid'
  return 'lo'
}

function formatScore(s) {
  return s?.toFixed?.(1) ?? '—'
}

function formatPip(s) {
  return s?.toFixed?.(0) ?? '—'
}

function roundTitle(rs) {
  const parts = []
  if (rs.target_reason) parts.push(`H→W: ${rs.target_reason}`)
  if (rs.candidate_reason) parts.push(`W→H: ${rs.candidate_reason}`)
  return parts.join('\n') || `round ${rs.round}`
}

function authorLabel(id) {
  if (id === 'target' || id === 'husband') return 'target'
  return id
}

function authorClass(id) {
  if (id === 'target' || id === 'husband') return 'who-target'
  return 'who-candidate'
}

function entryClass(entry) {
  return entry.kind === 'query' ? 'is-query' : 'is-answer'
}

// Auto-scroll to newest entry while expanded.
watch(
  () => conversation.value.length,
  () => {
    if (!convoOpen.value) return
    nextTick(() => {
      const el = convoPanel.value
      if (el) el.scrollTop = el.scrollHeight
    })
  },
)

// Also scroll on first expand.
watch(convoOpen, (open) => {
  if (!open) return
  nextTick(() => {
    const el = convoPanel.value
    if (el) el.scrollTop = el.scrollHeight
  })
})
</script>

<style lang="less" scoped>
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

.persona {
  background: #f7f5ee; border-radius: 2px; padding: 3px 5px;
  font-size: 10px; color: #333;
}
.persona-headline { margin-bottom: 2px; }
.persona-traits { display: flex; flex-wrap: wrap; gap: 2px; margin-bottom: 2px; }
.trait-chip {
  background: #eee; border: 1px solid #ccc; border-radius: 2px;
  padding: 0 4px; font-size: 9px; color: #444;
}
.persona-toggle {
  font-size: 9px; padding: 0 4px; border: none; background: transparent;
  color: #555; cursor: pointer;
  &:hover { color: #1a1a1a; }
}
.persona-full {
  margin: 2px 0 0; padding: 4px;
  background: #fff; border: 1px solid #e0e0d8; border-radius: 2px;
  font-family: "Monaco", monospace; font-size: 9px; color: #333;
  max-height: 120px; overflow: auto; white-space: pre-wrap;
}

.round-strip {
  display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
  background: #fafaf5; border-radius: 2px;
  padding: 2px 4px; font-size: 9px; color: #555;
}
.round-pip {
  display: inline-flex; align-items: center; gap: 3px;
  cursor: help;
}
.round-pip .rp-label { font-weight: 700; color: #444; }
.round-pip .rp-vals { font-variant-numeric: tabular-nums; }
.round-pip .rp-sep { color: #aaa; margin-left: 1px; }

.card-actions {
  display: flex; gap: 3px; margin-top: 2px; flex-wrap: wrap;
  .linkbtn {
    background: transparent; border: 1px solid #bbb; border-radius: 2px;
    padding: 1px 5px; font-size: 9px; cursor: pointer;
    &:hover { background: #ffe082; border-color: #d4a85d; }
    &.warn { color: #993c1d; }
    &:disabled { opacity: 0.4; cursor: not-allowed; }
  }
  .convo-toggle { margin-left: auto; }
}

.convo-panel {
  margin-top: 4px; padding: 4px 5px;
  background: #fafaf5; border: 1px solid #e0e0d8; border-radius: 2px;
  max-height: 200px; overflow: auto;
  font-size: 10px;
  display: flex; flex-direction: column; gap: 4px;
}
.convo-empty { padding: 2px; }
.convo-entry {
  border-left: 2px solid #ddd;
  padding: 2px 5px;
  &.is-query { border-left-color: #2c5d99; }
  &.is-answer { border-left-color: #d4a85d; }
}
.convo-meta {
  display: flex; align-items: center; gap: 5px;
  color: #666; margin-bottom: 1px;
}
.convo-meta .rnd { font-weight: 700; color: #444; }
.convo-meta .kind {
  text-transform: uppercase; font-size: 8px;
  padding: 0 3px; border-radius: 2px;
  &.query { background: #d6e4f5; color: #2c5d99; }
  &.answer { background: #f5e6cc; color: #6e4a14; }
}
.convo-meta .from-to { display: inline-flex; gap: 3px; align-items: center; }
.convo-meta .arrow { color: #aaa; }
.convo-meta .who-target { color: #2c5d99; font-weight: 600; }
.convo-meta .who-candidate { color: #b07c2c; font-weight: 600; }
.convo-text {
  color: #222; font-family: "Georgia", serif; line-height: 1.3;
  white-space: pre-wrap; word-break: break-word;
}
</style>
