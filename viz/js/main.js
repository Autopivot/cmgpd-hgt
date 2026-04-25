/* main.js — entry point and orchestrator for the HGT cohort viewer.
 *
 * Owner: Subagent D (integrator).
 *
 * Loading / call order at startup (DOMContentLoaded):
 *   1. loadAllCohorts()             — fetch ablated JSON for each known year.
 *   2. renderYearSelector()         — paint year-mini multiples in #year-selector.
 *   3. renderAll(state)             — build layout (cached), then call:
 *        renderHoneycomb(svg, layout, state)   [Subagent B]
 *        renderContours(svg, layout, weights, stride, state)   [Subagent C]
 *        applyFilterDimming(state) (CSS class only)
 *        dispatch 'state-changed' on window  (drill panel + linked views listen)
 *   4. bindInteractions(state, renderAll)     [interactions.js]
 *   5. initDrillPanel(state)                  [Subagent E — listens for events]
 *   6. initLinkedViews(state)                 [Subagent F — listens for events]
 *
 * Re-render rules (performance-critical):
 *   - Slider changes (channel weights, stride) → renderContoursOnly().
 *   - Filter chip changes                       → applyFilterDimming() only.
 *   - Ablation toggle                           → load swapped JSON, drop layout cache, full re-render.
 *   - Year selector                             → load that year, drop layout cache, full re-render.
 *
 * Cell selection events from #hc-svg (custom events 'cell-clicked' /
 * 'cell-hovered') are handled in interactions.js, which mutates `state` and
 * dispatches 'state-changed' / 'cell-hovered-state' on window.
 */

// Cache-buster `?v=N`: bump when fixing module bugs to defeat the browser's
// sticky ES-module cache during dev. Static import URLs are cached absolutely,
// so a query string is the simplest reliable invalidator.
import { buildHoneycomb }   from './cluster_layout.js?v=2';
import { renderHoneycomb }  from './honeycomb_render.js?v=2';
import { renderContours }   from './contour_render.js?v=2';
import { bindInteractions } from './interactions.js?v=2';
import { initDrillPanel }   from './drill_panel.js?v=2';
import { initLinkedViews }  from './linked_views.js?v=2';

// --- Known years. precompute.py writes a JSON per (year, ablation). ---
export const YEARS = [1882, 1885, 1888, 1903, 1906, 1909];

// --- Single global state. Mutated by interactions.js; read by renderAll. ---
export const state = {
  year: 1882,
  ablation: 'ablated',          // 'ablated' | 'unablated'
  cohort: null,                 // currently active cohort JSON
  layout: null,                 // honeycomb layout for the active (year, ablation)
  weights: { confidence: 1.0, patrilineal: 1.0, endogamy: 1.0 },
  stride: 7,
  filters: { era: null, hungarianCorrect: null },
  selectedCells: [],            // up to 2 cell ids
  hoveredCell: null,
};

// --- Caches keyed by `${year}::${ablation}`. ---
const cohortCache = new Map();
const layoutCache = new Map();

const cacheKey = (year, ablation) => `${year}::${ablation}`;

// ---------------------------------------------------------------------------
// Status line helpers
// ---------------------------------------------------------------------------

function setStatus(msg, isError = false) {
  const el = document.getElementById('status');
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle('error', !!isError);
}

// ---------------------------------------------------------------------------
// JSON loading
// ---------------------------------------------------------------------------

function cohortPath(year, ablation) {
  return ablation === 'unablated'
    ? `./data/cohort_${year}__unablated.json`
    : `./data/cohort_${year}.json`;
}

async function loadCohort(year, ablation) {
  const key = cacheKey(year, ablation);
  if (cohortCache.has(key)) return cohortCache.get(key);
  const path = cohortPath(year, ablation);
  try {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${path}`);
    const json = await res.json();
    cohortCache.set(key, json);
    return json;
  } catch (err) {
    setStatus(`Failed to load ${path}: ${err.message}`, true);
    throw err;
  }
}

async function loadAllCohorts() {
  setStatus('Loading cohorts.');
  const results = await Promise.allSettled(
    YEARS.map(y => loadCohort(y, 'ablated')),
  );
  const ok = results.filter(r => r.status === 'fulfilled').length;
  if (ok === 0) {
    setStatus('No cohorts loaded. Check viz/data/cohort_<year>.json.', true);
    return false;
  }
  setStatus(`Loaded ${ok}/${YEARS.length} ablated cohorts.`);
  return true;
}

// ---------------------------------------------------------------------------
// Year selector
// ---------------------------------------------------------------------------

function renderYearSelector() {
  const host = document.getElementById('year-selector');
  if (!host) return;
  host.innerHTML = '';
  for (const y of YEARS) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'year-tab' + (y === state.year ? ' active' : '');
    b.textContent = String(y);
    b.dataset.year = String(y);
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', y === state.year ? 'true' : 'false');
    host.appendChild(b);
  }
}

function refreshYearSelector() {
  const host = document.getElementById('year-selector');
  if (!host) return;
  for (const tab of host.querySelectorAll('.year-tab')) {
    const isActive = Number(tab.dataset.year) === state.year;
    tab.classList.toggle('active', isActive);
    tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
  }
}

function refreshAblationToggle() {
  const btn = document.getElementById('ablation-toggle');
  if (!btn) return;
  const isUn = state.ablation === 'unablated';
  btn.setAttribute('aria-pressed', isUn ? 'true' : 'false');
  btn.textContent = `Condition: ${state.ablation}`;
}

// ---------------------------------------------------------------------------
// Filter dimming (CSS-only re-render)
// ---------------------------------------------------------------------------

function pairMatchesFilters(pair, filters) {
  if (filters.era && pair.era !== filters.era) return false;
  if (filters.hungarianCorrect !== null) {
    const want = filters.hungarianCorrect === true || filters.hungarianCorrect === 'true';
    if (Boolean(pair.hungarian_correct) !== want) return false;
  }
  return true;
}

function applyFilterDimming(stateRef) {
  const svg = document.getElementById('hc-svg');
  if (!svg || !stateRef.cohort || !stateRef.layout) return;
  const { filters, cohort, layout } = stateRef;

  // No active filters → strip all dimming.
  const filtersActive = filters.era !== null || filters.hungarianCorrect !== null;
  if (!filtersActive) {
    svg.querySelectorAll('.cell-dim').forEach(el => el.classList.remove('cell-dim'));
    return;
  }

  // Build cell -> any-pair-matches map. Cluster ids on pairs match cell ids.
  const cellHasMatch = new Map();
  const pairs = cohort.pairs || [];
  const clusters = cohort.clusters || [];
  for (let i = 0; i < pairs.length; i++) {
    const cid = clusters[i];
    if (cid == null) continue;
    if (cellHasMatch.get(cid) === true) continue;
    if (pairMatchesFilters(pairs[i], filters)) {
      cellHasMatch.set(cid, true);
    } else if (!cellHasMatch.has(cid)) {
      cellHasMatch.set(cid, false);
    }
  }

  // Apply class. Cells render with a `data-cell-id` attribute by convention.
  const cells = svg.querySelectorAll('[data-cell-id]');
  cells.forEach(el => {
    const cid = Number(el.getAttribute('data-cell-id'));
    const matches = cellHasMatch.get(cid) === true;
    el.classList.toggle('cell-dim', !matches);
  });
}

// ---------------------------------------------------------------------------
// Render orchestration
// ---------------------------------------------------------------------------

async function ensureCohort() {
  const key = cacheKey(state.year, state.ablation);
  if (!cohortCache.has(key)) {
    setStatus(`Loading cohort ${state.year} (${state.ablation}).`);
    await loadCohort(state.year, state.ablation);
  }
  state.cohort = cohortCache.get(key) || null;
}

function ensureLayout() {
  if (!state.cohort) return;
  const key = cacheKey(state.year, state.ablation);
  if (layoutCache.has(key)) {
    state.layout = layoutCache.get(key);
    return;
  }
  const svg = document.getElementById('hc-svg');
  const vb = svg ? svg.viewBox.baseVal : { width: 960, height: 640 };
  const layout = buildHoneycomb(state.cohort, {
    width: vb.width || 960,
    height: vb.height || 640,
  });
  layoutCache.set(key, layout);
  state.layout = layout;
}

export async function renderAll(stateRef = state) {
  const svg = document.getElementById('hc-svg');
  if (!svg) return;

  await ensureCohort();
  if (!stateRef.cohort) return;

  ensureLayout();
  if (!stateRef.layout) return;

  // 1) Honeycomb base.
  renderHoneycomb(svg, stateRef.layout, stateRef);

  // 2) Contours over the honeycomb.
  console.time('contour');
  renderContours(svg, stateRef.layout, stateRef.weights, stateRef.stride, stateRef);
  console.timeEnd('contour');

  // 3) Apply filter dimming on the freshly-rendered cells.
  applyFilterDimming(stateRef);

  // 4) Notify listeners (drill panel, linked views).
  window.dispatchEvent(new CustomEvent('state-changed', { detail: { state: stateRef } }));

  setStatus(`Loaded ${stateRef.cohort.n_pairs} pairs for ${stateRef.year} (${stateRef.ablation}).`);
}

// Slider-only re-render path. Cheap.
export function renderContoursOnly(stateRef = state) {
  const svg = document.getElementById('hc-svg');
  if (!svg || !stateRef.layout) return;
  console.time('contour');
  renderContours(svg, stateRef.layout, stateRef.weights, stateRef.stride, stateRef);
  console.timeEnd('contour');
}

// Filter-only update. Pure CSS class flip.
export function applyFiltersOnly(stateRef = state) {
  applyFilterDimming(stateRef);
  window.dispatchEvent(new CustomEvent('state-changed', { detail: { state: stateRef, filtersOnly: true } }));
}

// Year / ablation switch — drop layout cache for the *previous* (year, ablation)
// only when the new one needs a fresh build; layoutCache is keyed so old cells
// can stay cached across toggling back-and-forth.
export async function switchYearOrAblation() {
  state.layout = null;
  await renderAll(state);
  refreshYearSelector();
  refreshAblationToggle();
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

window.addEventListener('DOMContentLoaded', async () => {
  renderYearSelector();
  refreshAblationToggle();

  const ok = await loadAllCohorts();
  if (!ok) return;

  await renderAll(state);

  bindInteractions(state, {
    renderAll,
    renderContoursOnly,
    applyFiltersOnly,
    switchYearOrAblation,
    loadCohort,
  });

  // Subagents E and F initialise themselves and listen for window events.
  try { initDrillPanel(state); } catch (e) { console.warn('drill panel init failed', e); }
  try { initLinkedViews(state); } catch (e) { console.warn('linked views init failed', e); }
});
