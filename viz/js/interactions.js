/* interactions.js — wires DOM inputs and SVG events to state mutations.
 *
 * Owner: Subagent D (integrator).
 *
 * Exports a single function `bindInteractions(state, callbacks)` where
 * callbacks is the bag of re-render functions exported by main.js:
 *   { renderAll, renderContoursOnly, applyFiltersOnly,
 *     switchYearOrAblation, loadCohort }
 */

export function bindInteractions(state, callbacks) {
  const {
    renderAll,
    renderContoursOnly,
    applyFiltersOnly,
    switchYearOrAblation,
  } = callbacks;

  // --- Year selector (delegated click on the container) ---------------------
  const yearHost = document.getElementById('year-selector');
  if (yearHost) {
    yearHost.addEventListener('click', (ev) => {
      const tab = ev.target.closest('.year-tab');
      if (!tab) return;
      const y = Number(tab.dataset.year);
      if (!Number.isFinite(y) || y === state.year) return;
      state.year = y;
      state.selectedCells = [];
      state.hoveredCell = null;
      switchYearOrAblation();
    });
  }

  // --- Ablation toggle ------------------------------------------------------
  const ablationBtn = document.getElementById('ablation-toggle');
  if (ablationBtn) {
    ablationBtn.addEventListener('click', () => {
      state.ablation = state.ablation === 'ablated' ? 'unablated' : 'ablated';
      state.selectedCells = [];
      state.hoveredCell = null;
      switchYearOrAblation();
    });
  }

  // --- Channel weight sliders (contour-only re-render) ----------------------
  const sliderMap = [
    ['w-confidence',  'confidence'],
    ['w-patrilineal', 'patrilineal'],
    ['w-endogamy',    'endogamy'],
  ];
  for (const [id, key] of sliderMap) {
    const input = document.getElementById(id);
    const out = document.getElementById(`${id}-val`);
    if (!input) continue;
    input.addEventListener('input', () => {
      const v = Number(input.value);
      state.weights[key] = v;
      if (out) out.textContent = v.toFixed(2);
      renderContoursOnly(state);
    });
  }

  // --- Stride slider --------------------------------------------------------
  const stride = document.getElementById('stride');
  const strideOut = document.getElementById('stride-val');
  if (stride) {
    stride.addEventListener('input', () => {
      const v = Number(stride.value);
      state.stride = v;
      if (strideOut) strideOut.textContent = String(v);
      renderContoursOnly(state);
    });
  }

  // --- Filter chips (CSS-only re-render) ------------------------------------
  const chipHost = document.getElementById('filter-chips');
  if (chipHost) {
    chipHost.addEventListener('click', (ev) => {
      const chip = ev.target.closest('.chip');
      if (!chip) return;
      const dim = chip.dataset.filter;
      const raw = chip.dataset.value;
      if (!dim) return;

      // Coerce 'true'/'false' strings to booleans for hungarianCorrect.
      const value = dim === 'hungarianCorrect'
        ? (raw === 'true')
        : raw;

      // Toggle: clicking the active chip in the same dimension clears it.
      const current = state.filters[dim];
      const same = current === value;
      // Clear sibling chips in same dimension.
      chipHost.querySelectorAll(`.chip[data-filter="${dim}"]`).forEach(c => c.classList.remove('active'));
      if (same) {
        state.filters[dim] = null;
      } else {
        state.filters[dim] = value;
        chip.classList.add('active');
      }
      applyFiltersOnly(state);
    });
  }

  // --- Custom events bubbled from #hc-svg cells ----------------------------
  // Subagent B's honeycomb_render emits 'cell-clicked' and 'cell-hovered'
  // CustomEvents on the SVG. We funnel them into state and broadcast.
  const svg = document.getElementById('hc-svg');
  if (svg) {
    svg.addEventListener('cell-clicked', (ev) => {
      // honeycomb_render.js emits the full cell record as detail; the cell's
      // identity field is `id` (matching cluster_layout.js's data model).
      // Accept legacy `cellId` too for forward-compat.
      const id = ev.detail && (ev.detail.cellId ?? ev.detail.id);
      if (id == null) return;
      // shift-key state lives on the original DOM event; honeycomb_render
      // doesn't forward it, so we read the most recent global modifier state.
      const shift = !!(ev.detail && ev.detail.shiftKey)
                 || !!(window.event && window.event.shiftKey);
      if (shift) {
        const exists = state.selectedCells.indexOf(id);
        if (exists >= 0) {
          state.selectedCells.splice(exists, 1);
        } else {
          state.selectedCells.push(id);
          if (state.selectedCells.length > 2) state.selectedCells.shift();
        }
      } else {
        state.selectedCells = [id];
      }
      window.dispatchEvent(new CustomEvent('state-changed', {
        detail: { state, reason: 'selection' },
      }));
    });

    svg.addEventListener('cell-hovered', (ev) => {
      const id = ev.detail ? (ev.detail.cellId ?? ev.detail.id) : null;
      state.hoveredCell = id == null ? null : id;
      window.dispatchEvent(new CustomEvent('cell-hovered-state', {
        detail: { state, cellId: state.hoveredCell },
      }));
    });
  }
}
