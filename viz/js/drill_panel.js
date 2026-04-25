// drill_panel.js — Subagent E
// Right-side drill panel for the honeycomb cell viewer.
// Renders pair-level detail for 0, 1, or 2 selected cells.

const COLUMNS = [
  { key: 'husband_id',         label: 'husband',     align: 'left',  width: 70 },
  { key: 'wife_id',            label: 'wife',        align: 'left',  width: 70 },
  { key: 'label',              label: 'label',       align: 'right', width: 36 },
  { key: 'score',              label: 'score',       align: 'right', width: 50 },
  { key: 'score_gap',          label: 'gap',         align: 'right', width: 50 },
  { key: 'rank_of_true_wife',  label: 'rank',        align: 'right', width: 40 },
  { key: 'hungarian_correct',  label: 'H. correct',  align: 'center',width: 56 },
  { key: 'same_lineage',       label: 'same lineage',align: 'center',width: 70 },
  { key: 'patri_path_count',   label: 'patri paths', align: 'right', width: 60 },
];

// Per-cell sort state. Map<cellId, {key, dir}> where dir is 'asc' | 'desc'.
const sortState = new Map();
const DEFAULT_SORT = { key: 'score_gap', dir: 'desc' };

function injectStyles() {
  if (document.querySelector('#drill-panel-styles')) return;
  const s = document.createElement('style');
  s.id = 'drill-panel-styles';
  s.textContent = `
    #drill-panel { box-sizing: border-box; padding: 10px; overflow: hidden;
      font-family: var(--font-sans, system-ui, sans-serif); display: flex;
      flex-direction: column; height: 100%; }
    #drill-panel .dp-section { display: flex; flex-direction: column;
      min-height: 0; flex: 1 1 auto; }
    #drill-panel .dp-section + .dp-section { margin-top: 10px;
      border-top: 1px solid #ddd; padding-top: 10px; }
    #drill-panel .dp-empty { color: #888; font-size: 12px; line-height: 1.5; }
    #drill-panel .dp-title { font-weight: 600; font-size: 12px;
      margin-bottom: 4px; }
    #drill-panel .dp-header { font-size: 11px; color: #333;
      margin-bottom: 6px; line-height: 1.4; }
    #drill-panel .dp-compare { font-size: 11px; color: #333;
      margin-bottom: 8px; line-height: 1.5; }
    #drill-panel .dp-clear { font-size: 11px; padding: 2px 8px;
      background: #f3f3f3; border: 1px solid #ccc; border-radius: 3px;
      cursor: pointer; float: right; }
    #drill-panel .dp-clear:hover { background: #e8e8e8; }
    #drill-panel .dp-table-wrap { overflow: auto; flex: 1 1 auto;
      min-height: 0; border: 1px solid #eee; }
    #drill-panel table.dp-table { border-collapse: collapse;
      table-layout: fixed; font-size: 11px; width: 100%; }
    #drill-panel table.dp-table th, #drill-panel table.dp-table td {
      border: 1px solid #eee; padding: 4px; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap; }
    #drill-panel table.dp-table th { background: #f7f7f7;
      cursor: pointer; user-select: none; text-align: left;
      position: sticky; top: 0; z-index: 1; }
    #drill-panel table.dp-table th .dp-arrow { color: #555;
      margin-left: 2px; }
    #drill-panel table.dp-table td.num,
    #drill-panel table.dp-table th.num {
      font-family: ui-monospace, Menlo, Consolas, monospace;
      text-align: right; }
    #drill-panel table.dp-table td.ctr,
    #drill-panel table.dp-table th.ctr { text-align: center; }
    #drill-panel tr.pos-correct { background: #f0f6ec; }
    #drill-panel tr.pos-wrong   { background: #fbecec; }
    #drill-panel .gap-pos { color: #2a6f2a; }
    #drill-panel .gap-neg { color: #a83232; }
  `;
  document.head.appendChild(s);
}

function fmtNum(v, dp) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const n = Number(v);
  const s = n.toFixed(dp);
  return n > 0 ? '+' + s : s;
}

function ellip(s, max) {
  if (s == null) return '';
  s = String(s);
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}

function getCellById(state, id) {
  if (!state || !state.layout || !Array.isArray(state.layout.cells)) return null;
  return state.layout.cells.find((c) => c.id === id) || null;
}

function getPairsForCell(state, cell) {
  if (!cell || !state.cohort || !Array.isArray(state.cohort.pairs)) return [];
  const ids = cell.pairIds || [];
  // Prefer a fast lookup if pairs are indexed by id.
  const byId = new Map();
  for (const p of state.cohort.pairs) byId.set(p.id, p);
  const out = [];
  for (const id of ids) {
    const p = byId.get(id);
    if (p) out.push(p);
  }
  return out;
}

function leadingChannel(cell) {
  // Use the precomputed cell aggregates to pick the strongest channel.
  // If unavailable, return '—'.
  if (!cell) return '—';
  const candidates = [
    ['confidence',   Math.abs(cell.confMean ?? 0)],
    ['score gap',    Math.abs(cell.meanScoreGap ?? 0)],
    ['patri paths',  Math.abs(cell.patriPathMean ?? 0)],
    ['same lineage', Math.abs(cell.sameLinFrac ?? 0)],
    ['positives',    Math.abs(cell.posRatio ?? 0)],
  ];
  candidates.sort((a, b) => b[1] - a[1]);
  return candidates[0][0];
}

function compareValues(a, b, dir) {
  // Robust comparator: nulls last; booleans by value; numbers numeric;
  // otherwise string.
  const an = a === null || a === undefined;
  const bn = b === null || b === undefined;
  if (an && bn) return 0;
  if (an) return 1;   // null always last regardless of dir
  if (bn) return -1;
  let cmp;
  if (typeof a === 'number' && typeof b === 'number') cmp = a - b;
  else if (typeof a === 'boolean' && typeof b === 'boolean')
    cmp = (a === b) ? 0 : (a ? 1 : -1);
  else cmp = String(a).localeCompare(String(b));
  return dir === 'asc' ? cmp : -cmp;
}

function sortPairs(pairs, sort) {
  const key = sort.key;
  const dir = sort.dir;
  const copy = pairs.slice();
  copy.sort((x, y) => compareValues(x[key], y[key], dir));
  return copy;
}

function rowClass(p) {
  if (p.label === 1 && p.hungarian_correct === true) return 'pos-correct';
  if (p.label === 1 && p.hungarian_correct === false) return 'pos-wrong';
  return '';
}

function buildTable(cellId, pairs, sort) {
  const wrap = document.createElement('div');
  wrap.className = 'dp-table-wrap';

  const table = document.createElement('table');
  table.className = 'dp-table';

  // colgroup so widths are identical between cell A and cell B tables.
  const colgroup = document.createElement('colgroup');
  for (const c of COLUMNS) {
    const col = document.createElement('col');
    col.style.width = c.width + 'px';
    colgroup.appendChild(col);
  }
  table.appendChild(colgroup);

  const thead = document.createElement('thead');
  const trh = document.createElement('tr');
  for (const c of COLUMNS) {
    const th = document.createElement('th');
    if (c.align === 'right') th.classList.add('num');
    else if (c.align === 'center') th.classList.add('ctr');
    th.textContent = c.label;
    if (sort.key === c.key) {
      const arrow = document.createElement('span');
      arrow.className = 'dp-arrow';
      arrow.textContent = sort.dir === 'asc' ? ' ▲' : ' ▼';
      th.appendChild(arrow);
    }
    th.addEventListener('click', () => {
      const cur = sortState.get(cellId) || { ...DEFAULT_SORT };
      let next;
      if (cur.key === c.key) {
        next = { key: c.key, dir: cur.dir === 'asc' ? 'desc' : 'asc' };
      } else {
        // First click on a new column: numeric desc, string asc.
        const numericCols = ['label', 'score', 'score_gap',
          'rank_of_true_wife', 'patri_path_count'];
        next = { key: c.key,
          dir: numericCols.includes(c.key) ? 'desc' : 'asc' };
      }
      sortState.set(cellId, next);
      // Re-render in place by dispatching a state-changed event so the
      // panel rebuilds; this keeps a single render path.
      window.dispatchEvent(new CustomEvent('state-changed',
        { detail: { reason: 'drill-sort' } }));
    });
    trh.appendChild(th);
  }
  thead.appendChild(trh);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  for (const p of pairs) {
    const tr = document.createElement('tr');
    const rc = rowClass(p);
    if (rc) tr.className = rc;

    // husband
    {
      const td = document.createElement('td');
      td.textContent = ellip(p.husband_id, 12);
      td.title = p.husband_id ?? '';
      tr.appendChild(td);
    }
    // wife
    {
      const td = document.createElement('td');
      td.textContent = ellip(p.wife_id, 12);
      td.title = p.wife_id ?? '';
      tr.appendChild(td);
    }
    // label
    {
      const td = document.createElement('td');
      td.className = 'num';
      td.textContent = (p.label === 1 || p.label === 0) ? String(p.label) : '—';
      tr.appendChild(td);
    }
    // score
    {
      const td = document.createElement('td');
      td.className = 'num';
      td.textContent = (p.score === null || p.score === undefined)
        ? '—' : Number(p.score).toFixed(2);
      tr.appendChild(td);
    }
    // gap (color-coded)
    {
      const td = document.createElement('td');
      td.className = 'num';
      const v = p.score_gap;
      if (v === null || v === undefined) {
        td.textContent = '—';
      } else {
        const span = document.createElement('span');
        const n = Number(v);
        span.textContent = fmtNum(n, 2);
        if (n > 0) span.className = 'gap-pos';
        else if (n < 0) span.className = 'gap-neg';
        td.appendChild(span);
      }
      tr.appendChild(td);
    }
    // rank
    {
      const td = document.createElement('td');
      td.className = 'num';
      td.textContent = (p.rank_of_true_wife === null
        || p.rank_of_true_wife === undefined) ? '—'
        : String(p.rank_of_true_wife);
      tr.appendChild(td);
    }
    // hungarian_correct
    {
      const td = document.createElement('td');
      td.className = 'ctr';
      if (p.hungarian_correct === true) td.textContent = 'yes';
      else if (p.hungarian_correct === false) td.textContent = 'no';
      else td.textContent = '—';
      tr.appendChild(td);
    }
    // same_lineage
    {
      const td = document.createElement('td');
      td.className = 'ctr';
      td.textContent = (p.same_lineage === true) ? 'yes'
        : (p.same_lineage === false) ? 'no' : '—';
      tr.appendChild(td);
    }
    // patri_path_count
    {
      const td = document.createElement('td');
      td.className = 'num';
      td.textContent = (p.patri_path_count === null
        || p.patri_path_count === undefined)
        ? '—' : String(p.patri_path_count);
      tr.appendChild(td);
    }

    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function buildHeader(cell, pairs) {
  const div = document.createElement('div');
  div.className = 'dp-header';
  const meanGap = cell.meanScoreGap;
  const gapStr = (meanGap === null || meanGap === undefined)
    ? '—' : fmtNum(meanGap, 2);
  div.innerHTML =
    `<div class="dp-title">Cell #${cell.id} · Cluster ${cell.cluster} `
    + `· ${pairs.length} pairs</div>`
    + `<div>Mean score gap: ${gapStr}</div>`
    + `<div>Leading channel: ${leadingChannel(cell)}</div>`;
  return div;
}

function buildCompareHeader(cellA, cellB) {
  const div = document.createElement('div');
  div.className = 'dp-compare';
  const fmtCell = (c) => {
    if (!c) return 'n/a';
    const g = (c.meanScoreGap === null || c.meanScoreGap === undefined)
      ? '—' : fmtNum(c.meanScoreGap, 2);
    return `cluster ${c.cluster}, n=${(c.pairIds || []).length}, mean gap ${g}`;
  };
  div.innerHTML =
    `<div class="dp-title">Compare</div>`
    + `<div>Cell A: ${fmtCell(cellA)}</div>`
    + `<div>Cell B: ${fmtCell(cellB)}</div>`;
  return div;
}

function buildClearButton(state) {
  const btn = document.createElement('button');
  btn.className = 'dp-clear';
  btn.type = 'button';
  btn.textContent = 'Clear';
  btn.addEventListener('click', () => {
    state.selectedCells = [];
    window.dispatchEvent(new CustomEvent('state-changed',
      { detail: { reason: 'drill-clear' } }));
  });
  return btn;
}

function renderEmpty(root) {
  const sec = document.createElement('div');
  sec.className = 'dp-section';
  sec.innerHTML =
    `<div class="dp-title">Drill panel</div>`
    + `<div class="dp-empty">`
    + `Click a cell on the honeycomb to see the pairs in it.<br><br>`
    + `Shift+click adds a second cell for side-by-side comparison.`
    + `</div>`;
  root.appendChild(sec);
}

function renderOne(root, state, cell) {
  // Top bar with Clear button.
  const top = document.createElement('div');
  top.style.minHeight = '20px';
  top.appendChild(buildClearButton(state));
  // Clear floats right; add a clearfix.
  const cf = document.createElement('div');
  cf.style.clear = 'both';
  top.appendChild(cf);
  root.appendChild(top);

  if (!cell) {
    const warn = document.createElement('div');
    warn.className = 'dp-empty';
    warn.textContent = 'Selected cell not found in the current layout.';
    root.appendChild(warn);
    return;
  }

  const pairs = getPairsForCell(state, cell);
  const sort = sortState.get(cell.id) || { ...DEFAULT_SORT };
  if (!sortState.has(cell.id)) sortState.set(cell.id, sort);
  const sorted = sortPairs(pairs, sort);

  const sec = document.createElement('div');
  sec.className = 'dp-section';
  sec.appendChild(buildHeader(cell, pairs));
  sec.appendChild(buildTable(cell.id, sorted, sort));
  root.appendChild(sec);
}

function renderTwo(root, state, cellA, cellB) {
  // Top bar: Clear button + compare summary.
  const top = document.createElement('div');
  top.appendChild(buildClearButton(state));
  top.appendChild(buildCompareHeader(cellA, cellB));
  // clearfix
  const cf = document.createElement('div');
  cf.style.clear = 'both';
  top.appendChild(cf);
  root.appendChild(top);

  for (const cell of [cellA, cellB]) {
    const sec = document.createElement('div');
    sec.className = 'dp-section';
    if (!cell) {
      const warn = document.createElement('div');
      warn.className = 'dp-empty';
      warn.textContent = 'Selected cell not found.';
      sec.appendChild(warn);
      root.appendChild(sec);
      continue;
    }
    const pairs = getPairsForCell(state, cell);
    const sort = sortState.get(cell.id) || { ...DEFAULT_SORT };
    if (!sortState.has(cell.id)) sortState.set(cell.id, sort);
    const sorted = sortPairs(pairs, sort);
    sec.appendChild(buildHeader(cell, pairs));
    sec.appendChild(buildTable(cell.id, sorted, sort));
    root.appendChild(sec);
  }
}

function pruneSortState(state) {
  // Drop sort state for cells no longer selected so memory doesn't grow
  // unbounded across cohort changes.
  const sel = new Set(state.selectedCells || []);
  for (const k of Array.from(sortState.keys())) {
    if (!sel.has(k)) sortState.delete(k);
  }
}

function render(state) {
  const root = document.querySelector('#drill-panel');
  if (!root) return;
  // Clear prior content.
  while (root.firstChild) root.removeChild(root.firstChild);

  pruneSortState(state);

  const sel = Array.isArray(state.selectedCells) ? state.selectedCells : [];
  if (sel.length === 0) {
    renderEmpty(root);
    return;
  }
  if (sel.length === 1) {
    const cell = getCellById(state, sel[0]);
    renderOne(root, state, cell);
    return;
  }
  // Two or more: use first two.
  const cellA = getCellById(state, sel[0]);
  const cellB = getCellById(state, sel[1]);
  renderTwo(root, state, cellA, cellB);
}

export function initDrillPanel(state) {
  injectStyles();
  const root = document.querySelector('#drill-panel');
  if (!root) {
    // No mount point; nothing to do. Silent — D owns the DOM.
    return;
  }
  // Initial render.
  render(state);
  // Re-render on state changes.
  window.addEventListener('state-changed', () => {
    try {
      render(state);
    } catch (err) {
      // Surface the error in the panel so it's visible without crashing
      // the page.
      while (root.firstChild) root.removeChild(root.firstChild);
      const e = document.createElement('div');
      e.className = 'dp-empty';
      e.textContent = 'Drill panel error: ' + (err && err.message
        ? err.message : String(err));
      root.appendChild(e);
      // eslint-disable-next-line no-console
      console.error('[drill_panel] render failed', err);
    }
  });
}
