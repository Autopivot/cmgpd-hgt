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
 * View 5 — agent battle (placeholder).
 * Until the live FastAPI + LLM backend lands, returns a static fixture.
 */
export async function getAgentRound({ year, ablation = 'ablated', pair_id } = {}) {
  const pair = await getPair({ year, ablation, id: pair_id })
  if (!pair) return null
  return {
    pair_id,
    rounds: [
      { agent: 'paternal-prior', score: pair.score, note: 'baseline patrilineal scaffold' },
      { agent: 'macro-temporal', score: pair.score - 0.1, note: 'cohort year + grain prices' },
      { agent: 'lineage-consistency', score: pair.same_lineage ? -1.5 : pair.score, note: pair.same_lineage ? 'same lineage penalty' : 'cross-lineage ok' },
    ],
    final_score: pair.score,
    accept: pair.hungarian_correct === true,
  }
}

/**
 * View 6 — rule weights (macro/micro motifs).
 * Static configuration for now; real backend will accept POST to update.
 */
export async function getRules() {
  return {
    macro: [
      { id: 'paternal_lineage', label: 'Paternal lineage proximity', weight: 1.0 },
      { id: 'sibling_overlap',  label: 'Shared siblings',            weight: 1.0 },
      { id: 'household_share',  label: 'Same household history',     weight: 1.0 },
      { id: 'banner_match',     label: 'Same banner',                weight: 0.5 },
      { id: 'macro_era',        label: 'Cohort year + grain prices', weight: 0.8 },
    ],
    motifs: [
      { id: 'm1_father_brother', title: 'Father → brother → wife',     enabled: true,  example_count: 2103 },
      { id: 'm2_uncle_in_law',   title: 'Uncle-in-law triangle',       enabled: true,  example_count:  894 },
      { id: 'm3_same_household', title: 'Pre-marriage co-residence',   enabled: false, example_count: 1456 },
      { id: 'm4_banner_endog',   title: 'Banner endogamy chain',       enabled: true,  example_count:  327 },
    ],
  }
}
