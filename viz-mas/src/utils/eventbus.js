import mitt from 'mitt'

// Cross-view events:
//   'hex-select'      { binKey, bounds, pairs: [{ id, husband_id, wife_id, score, ... }] }
//   'hex-clear'
//   'cohort-changed'  { year, ablation }
//   'pair-click'      { id, husband_id, wife_id }
//   'full-screen'     'v1' | 'v2' | 'v3' | 'v4' | 'v5' | 'v6'
export default mitt()
