// Data client.
//
// Two modes:
//   1. Live backend at /api (FastAPI at 127.0.0.1:8001 with HGT inference) —
//      not yet implemented for this dataset. health() will fail and the app
//      falls back to mode 2.
//   2. Static fallback: fetch cohort_<year>.json out of /data/. The cohort
//      JSONs are precomputed by viz/data/precompute.py against the trained
//      checkpoints, so they already contain real model outputs (score,
//      score_gap, hungarian_correct, lineage_*). Acts as the offline MAS
//      data source until the live backend lands.
//
// The two modes return the same shapes (relations, embeddings, persons,
// metrics) so view components don't care which is active.

import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

// Cohort cache: year+ablation → loaded JSON
const cohortCache = new Map()
const cohortKey = (year, ablation) => `${year}__${ablation}`

export const ALL_YEARS = [1882, 1885, 1888, 1903, 1906, 1909]
export const ALL_ABLATIONS = ['ablated', 'unablated']

/** Load a cohort JSON from /data/. Cached. */
export async function loadCohort(year, ablation = 'ablated') {
  const k = cohortKey(year, ablation)
  if (cohortCache.has(k)) return cohortCache.get(k)
  const suffix = ablation === 'unablated' ? '__unablated' : ''
  const url = `./data/cohort_${year}${suffix}.json`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`)
  const json = await res.json()
  cohortCache.set(k, json)
  return json
}

/** Best-effort backend liveness probe. */
export async function health() {
  try { await http.get('/health'); return true }
  catch { return false }
}

// ── Adapters from cohort-JSON shape to the API-style endpoints ──────────

/**
 * View 1 — overview metrics.
 * Returns aggregate completion stats per cohort year.
 */
export async function getMetrics({ ablation = 'ablated' } = {}) {
  const out = []
  for (const y of ALL_YEARS) {
    try {
      const c = await loadCohort(y, ablation)
      const positives = c.pairs.filter(p => p.label === 1)
      const totalPos = positives.length
      const correct = positives.filter(p => p.hungarian_correct === true).length
      const top1 = positives.filter(p => p.rank_of_true_wife === 1).length
      const top10 = positives.filter(p =>
        Number.isFinite(p.rank_of_true_wife) && p.rank_of_true_wife <= 10
      ).length
      const mrr = positives.length === 0 ? 0 :
        positives.reduce((s, p) => {
          const r = p.rank_of_true_wife
          return s + (Number.isFinite(r) && r > 0 ? 1 / r : 0)
        }, 0) / positives.length
      out.push({
        year: y,
        n_pairs: c.n_pairs,
        n_positives: totalPos,
        hungarian_recall_at_1: totalPos ? correct / totalPos : 0,
        top1_recall: totalPos ? top1 / totalPos : 0,
        top10_recall: totalPos ? top10 / totalPos : 0,
        mrr,
        completion: totalPos ? correct / totalPos : 0,
      })
    } catch (e) {
      out.push({ year: y, error: String(e) })
    }
  }
  return out
}

/**
 * View 2 — sorted list of matched pairs for a single cohort.
 * Default: positives only, sorted by score descending.
 */
export async function getMatches({
  year, ablation = 'ablated', limit = 300, positives_only = true,
} = {}) {
  const c = await loadCohort(year, ablation)
  let pairs = c.pairs
  if (positives_only) pairs = pairs.filter(p => p.label === 1)
  pairs = [...pairs].sort((a, b) => b.score - a.score)
  return pairs.slice(0, limit).map(p => ({
    id: p.id,
    male_idx: p.husband_id,
    female_idx: p.wife_id,
    score: p.score,
    score_gap: p.score_gap,
    rank_of_true_wife: p.rank_of_true_wife,
    hungarian_correct: p.hungarian_correct,
    same_lineage: p.same_lineage,
    era: p.era,
    label: p.label,
    pair_type: p.label === 1 ? 'gt' : 'pred',
  }))
}

/**
 * View 3 — embedding scatter + cluster info.
 * Returns mds_coords + clusters + per-pair metadata for scatter rendering.
 */
export async function getEmbedding({ year, ablation = 'ablated' } = {}) {
  const c = await loadCohort(year, ablation)
  return {
    year,
    ablation,
    n_pairs: c.n_pairs,
    k_clusters: c.k_clusters,
    mds_coords: c.mds_coords,
    clusters: c.clusters,
    pairs: c.pairs,  // full list — caller computes whatever per-cell aggregates it needs
    // Training-cohort positives projected through the same scorer head and
    // jointly MDS'd with the cohort's pairs (precompute.py since the
    // joint-MDS patch). V3 normalizes these into the canonical [0,1]² space
    // and renders them as a density heatmap behind the cells/dots.
    train_ref_coords: c.train_ref_coords || [],
    train_ref_n: c.train_ref_n || 0,
  }
}

/**
 * View 4 — bipartite person detail.
 * Returns the husband + wife of a single pair plus their per-cohort context.
 */
export async function getPair({ year, ablation = 'ablated', id } = {}) {
  const c = await loadCohort(year, ablation)
  return c.pairs[id] || null
}

/**
 * View 5 — multi-agent LLM negotiation.
 *
 * Per-husband flow: POST /api/negotiate/{husband_id} kicks the negotiator
 * off in the background, then we open a WebSocket at
 * /api/negotiate/{husband_id}/stream to receive events as they happen.
 *
 * Event shapes (matches server/mas/negotiator.py).
 *
 * Legacy / fallback frames (kept as no-ops in the new flow):
 *   { type: 'start',            husband_id, year, ablation }
 *   { type: 'stage', stage: 'profile',       profile }
 *   { type: 'stage', stage: 'filter',        funnel, candidates: [{person, pre_score, hgt_label, score_gap}] }
 *   { type: 'agent_prompt',     side: 'target'|'candidate', person_id, prompt }
 *   { type: 'agent_token',      side, person_id, delta }
 *   { type: 'target_scores',    scores: [{ candidate_id, score, reason }] }    // pre-6-round
 *   { type: 'bilateral_scores', scores: { candidate_id: { score, reason } } }  // pre-6-round
 *   { type: 'committed',        match }
 *   { type: 'hint_ack',         role, text }
 *   { type: 'error',            error }
 *   { type: 'done' }
 *
 * 6-round bilateral negotiation frames:
 *   { type: 'round_start',      round: 1..6, label: 'persona'|'impressions'|'deep-dive'|'rebuttals'|'alignment'|'final' }
 *   { type: 'narrative',        person_id, birth_year?, events: [...], income: [...] }
 *   { type: 'persona',          person_id, resume: { headline, traits, values, red_flags }, motifs: [motif_id, ...] }
 *   { type: 'query',            from: 'target'|'c-XXX', to: 'c-XXX'|'target', text }
 *   { type: 'answer',           from: 'c-XXX'|'target', to: 'target'|'c-XXX', text }
 *   { type: 'round_scores',     round: N, pairs: [{ candidate_id, target_score, candidate_score, target_reason, candidate_reason }] }
 *   { type: 'round_paused',     round: N, awaiting: 'user_advance' }
 *   { type: 'final_ranking',    ranking: [{ candidate_id, target_score, candidate_score, final_score, lambda }], chosen?: {...} }
 */
export async function startNegotiation({ husband_id, year, ablation = 'ablated', auto_commit = false } = {}) {
  const r = await http.post(`/negotiate/${encodeURIComponent(husband_id)}`, {
    year, ablation, auto_commit,
  })
  return r.data
}

export function openNegotiationStream(husband_id) {
  const wsProto = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${wsProto}://${location.host}/api/negotiate/${encodeURIComponent(husband_id)}/stream`)
}

export async function sendNegotiationHint(husband_id, text, role = 'all', round = 0) {
  const r = await http.post(`/negotiate/${encodeURIComponent(husband_id)}/hint`, {
    text, role, round,
  })
  return r.data
}

/**
 * Resume a paused negotiation. Sent in response to a `round_paused` frame
 * once the user clicks "Approve & Advance"; the server then drives the
 * next round.
 */
export async function advanceRound(husband_id) {
  const r = await http.post(`/negotiate/${encodeURIComponent(husband_id)}/advance`)
  return r.data
}

/**
 * Life-history payload for a single person (events + income series).
 * Returns an empty stub if the backend is offline / lacks a narrative
 * for this person -- callers can render the panel either way.
 */
export async function getNarrative(person_id, year) {
  try {
    const r = await http.get(`/narrative/${encodeURIComponent(person_id)}`, { params: { year } })
    return r.data
  } catch {
    return { person_id, birth_year: null, events: [], income: [] }
  }
}

/**
 * Cleaned-parquet profile for one person. Used by V4's click-popup and
 * by V5 to pre-fill the husband header before the negotiation streams.
 * Returns { id, sex, birth_year, banner_id, community_id, household_id }
 * (or a {sex:'?'} stub if the backend is offline).
 */
export async function getProfile(person_id) {
  try {
    const r = await http.get(`/profile/${encodeURIComponent(person_id)}`)
    return r.data
  } catch {
    return { id: person_id, sex: '?', birth_year: null,
             banner_id: null, community_id: null, household_id: null }
  }
}

export async function overrideMatch(husband_id, wife_id, score, note, year, ablation) {
  const r = await http.post(`/negotiate/${encodeURIComponent(husband_id)}/override`, {
    wife_id, score, note, year, ablation,
  })
  return r.data
}

/**
 * V2 — full map of currently-accepted relations: { husband_id → record }.
 * Each record has { husband_id, wife_id, score, source, year, ablation, ts }.
 */
export async function getAccepted() {
  try {
    const r = await http.get('/negotiate/accepted')
    return r.data || {}
  } catch {
    return {}
  }
}

/**
 * V2 restore — undo a prior accept so the (h, w) edge re-enters V3/V4 and
 * V1's curve recomputes as if it never happened.
 */
export async function restoreMatch(husband_id) {
  const r = await http.post(`/negotiate/${encodeURIComponent(husband_id)}/restore`)
  return r.data
}

/** V1 learning-curve series + HGT static baseline for the given cohort. */
export async function getEvalProgress({ year, ablation = 'ablated' } = {}) {
  try {
    const r = await http.get('/eval/progress', { params: { year, ablation } })
    return r.data
  } catch {
    return {
      year, ablation,
      hgt_baseline: { recall_at_1: 0, n_positives: 0 },
      trajectory: [],
      n_accepted_total: 0,
      n_eligible_total: 0,
      n_correct_total: 0,
      mas_recall_at_1_now: null,
    }
  }
}

export async function resetEvalLog() {
  try { await http.post('/eval/reset') } catch {}
}

export async function getLLMConfig() {
  try { const r = await http.get('/llm_config'); return r.data }
  catch { return { use_llm: false, model: 'qwen-plus-2025-04-28', api_key_set: false } }
}

export async function setLLMConfig({ api_key = null, model = null } = {}) {
  const r = await http.post('/llm_config', { api_key, model })
  return r.data
}

/** SHAP-style waterfall — heuristic decomposition of the pair's logit. */
export async function getShap({ year, ablation = 'ablated', pair_id } = {}) {
  // Try backend first.
  try {
    const r = await http.get(`/shap/${pair_id}`, { params: { year, ablation } })
    return r.data
  } catch {
    // Local fallback — mirrors server/main.py:_shap_components()
    const pair = await getPair({ year, ablation, id: pair_id })
    if (!pair) return null
    const w = await getRules()
    const m = w.macro_obj
    const patri = pair.patri_path_count || 0
    const sameLin = !!pair.same_lineage
    const era = pair.era || 'regular'
    const eraScore = { regular: 0.4, catchup: 0, late: 0.2 }[era] ?? 0
    const parts = [
      { label: 'bias',                value: -1.0 },
      { label: 'paternal lineage',    value: m.paternal_lineage * (0.6 * patri) },
      { label: 'sibling overlap',     value: m.sibling_overlap  * (patri >= 2 ? 0.35 : 0) },
      { label: 'household share',     value: m.household_share  * (patri >= 3 ? 0.45 : 0) },
      { label: 'banner match',        value: m.banner_match     * 0.3 },
      { label: 'macro era',           value: m.macro_era        * eraScore },
      { label: 'endogamy penalty',    value: sameLin ? -2.0 : 0 },
    ]
    const sumPredicted = parts.reduce((s, p) => s + p.value, 0)
    const ratio = sumPredicted !== 0 ? pair.score / sumPredicted : 1
    parts.forEach(p => { p.scaled = p.value * ratio })
    parts.push({ label: 'FINAL (logit)', value: pair.score, scaled: pair.score, is_total: true })
    parts.push({ label: 'score gap',     value: pair.score_gap, scaled: pair.score_gap, is_total: true })
    return {
      pair_id,
      husband_id: pair.husband_id,
      wife_id: pair.wife_id,
      components: parts,
    }
  }
}

/**
 * View 6 — rule weights (macro/micro motifs). Two cooperating shapes:
 *   `macro`  — array form, used by V6's UI rendering loop
 *   `macro_obj` — object form keyed by `id`, used by SHAP/agent computation
 * Both are kept in sync. POST writes accept either.
 */
const RULE_DEFAULTS = {
  macro: [
    { id: 'paternal_lineage', label: 'Paternal lineage proximity', weight: 1.0 },
    { id: 'sibling_overlap',  label: 'Shared siblings',            weight: 1.0 },
    { id: 'household_share',  label: 'Same household history',     weight: 1.0 },
    { id: 'banner_match',     label: 'Same banner',                weight: 0.5 },
    { id: 'macro_era',        label: 'Cohort year + grain prices', weight: 0.8 },
  ],
  motifs: [
    {
      id: 'm1_father_brother', title: 'Father → brother → wife', enabled: true, example_count: 2103,
      example: {
        num_nodes: 4, src_local: 0, dst_local: 3,
        drnl_labels: [1, 2, 2, 1],
        edges: [[0, 1], [1, 2], [2, 3]],
        edge_types: ['r_fs', 'r_sib', 'r_hw'],
      },
    },
    {
      id: 'm2_uncle_in_law', title: 'Uncle-in-law triangle', enabled: true, example_count: 894,
      example: {
        num_nodes: 5, src_local: 0, dst_local: 4,
        drnl_labels: [1, 2, 3, 2, 1],
        edges: [[0, 1], [1, 2], [2, 3], [3, 4]],
        edge_types: ['r_fs', 'r_sib', 'r_fd', 'r_hw'],
      },
    },
    {
      id: 'm3_same_household', title: 'Pre-marriage co-residence', enabled: false, example_count: 1456,
      example: {
        num_nodes: 3, src_local: 0, dst_local: 2,
        drnl_labels: [1, 0, 1],
        edges: [[0, 1], [1, 2], [0, 2]],
        edge_types: ['r_hh', 'r_hh', 'r_hw'],
      },
    },
    {
      id: 'm4_banner_endog', title: 'Banner endogamy chain', enabled: true, example_count: 327,
      example: {
        num_nodes: 4, src_local: 0, dst_local: 3,
        drnl_labels: [1, 0, 0, 1],
        edges: [[0, 1], [1, 2], [2, 3]],
        edge_types: ['r_cb', 'r_cb', 'r_hw'],
      },
    },
  ],
}

let _ruleCache = null

function _normalize(rules) {
  // Return the (macro, motifs, macro_obj) tuple from any of the input shapes.
  const macro = Array.isArray(rules.macro)
    ? rules.macro
    : RULE_DEFAULTS.macro.map(d => ({ ...d, weight: rules.macro?.[d.id] ?? d.weight }))
  const motifs = Array.isArray(rules.motifs)
    ? rules.motifs.map((m, i) => ({ ...RULE_DEFAULTS.motifs[i], ...m }))
    : RULE_DEFAULTS.motifs.map(d => ({ ...d, enabled: rules.motifs?.[d.id] ?? d.enabled }))
  const macro_obj = {}
  for (const r of macro) macro_obj[r.id] = r.weight
  return { macro, motifs, macro_obj }
}

/** Load current rule state. Tries the backend; falls back to defaults. */
export async function getRules() {
  if (_ruleCache) return _ruleCache
  try {
    const r = await http.get('/rules')
    _ruleCache = _normalize(r.data)
  } catch {
    _ruleCache = _normalize({ macro: {}, motifs: {} })
  }
  return _ruleCache
}

/** Push macro / motif updates. Accepts {macro: {id: weight}, motifs: {id: bool}}. */
export async function postRules(body) {
  try {
    const r = await http.post('/rules', body)
    _ruleCache = _normalize(r.data)
  } catch {
    // Local-only update — apply to cached state so SHAP/agents pick it up.
    const cur = await getRules()
    if (body.macro) {
      for (const r of cur.macro) {
        if (body.macro[r.id] != null) r.weight = body.macro[r.id]
      }
    }
    if (body.motifs) {
      for (const m of cur.motifs) {
        if (body.motifs[m.id] != null) m.enabled = body.motifs[m.id]
      }
    }
    _ruleCache = _normalize(cur)
  }
  return _ruleCache
}
