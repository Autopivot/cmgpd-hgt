<template>
  <div class="rwe" :class="{ readonly }">
    <div v-if="!husband?.husband_id" class="empty">
      select a husband in V4 to set rule weights
    </div>
    <template v-else>
      <div class="weights-grid">
        <div v-for="m in METRICS" :key="m.key" class="weight-row">
          <label class="lbl tiny" :title="m.label">{{ m.short }}</label>
          <input class="slider" type="range" min="0" max="2" step="0.05"
                 v-model.number="state.weights[m.key]"
                 :disabled="readonly" @input="onChange" />
          <span class="val tiny">{{ state.weights[m.key].toFixed(2) }}</span>
        </div>
      </div>
      <div class="motif-grid">
        <div class="motif-head tiny muted">motifs</div>
        <label v-for="mid in MOTIF_IDS" :key="mid" class="motif-chk tiny"
               :title="MOTIF_TIPS[mid] || mid"
               :class="{ on: state.motifs_enabled[mid] }">
          <input type="checkbox"
                 v-model="state.motifs_enabled[mid]"
                 :disabled="readonly" @change="onChange" />
          <span>{{ MOTIF_LABELS[mid] || mid }}</span>
        </label>
      </div>
      <div v-if="readonly" class="ro-banner tiny muted">
        read-only · loaded from 1882 cell profile
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'
import bus from '../../utils/eventbus.js'

const props = defineProps({
  husband: { type: Object, default: null },
  readonly: { type: Boolean, default: false },
})

const METRICS = [
  { key: 'paternal_lineage_proximity', short: 'paternal',   label: 'paternal lineage proximity' },
  { key: 'shared_siblings',            short: 'siblings',   label: 'shared siblings' },
  { key: 'same_household_history',     short: 'household',  label: 'same household history' },
  { key: 'same_banner',                short: 'banner',     label: 'same banner' },
]

const MOTIF_IDS = [
  'M01_direct_sibling', 'M02_shared_father_via_fs_fd',
  'M03_two_degree_sibling_chain', 'M10_household_mediated_daughter',
  'CTX_same_banner', 'CTX_same_community',
  'CTX_co_resident', 'CTX_same_region',
]
const MOTIF_LABELS = {
  M01_direct_sibling: 'M01 sib',
  M02_shared_father_via_fs_fd: 'M02 shared-father',
  M03_two_degree_sibling_chain: 'M03 sib-chain',
  M10_household_mediated_daughter: 'M10 hh-daughter',
  CTX_same_banner: 'banner',
  CTX_same_community: 'community',
  CTX_co_resident: 'co-resident',
  CTX_same_region: 'region',
}
const MOTIF_TIPS = {
  M01_direct_sibling: 'Direct sibling via r_sib',
  M02_shared_father_via_fs_fd: 'Shared FATHER_ID through r_fs+r_fd',
  M03_two_degree_sibling_chain: '2-degree sibling chain',
  M10_household_mediated_daughter: "Co-resident's daughter (household-mediated)",
  CTX_same_banner: 'Same banner affiliation',
  CTX_same_community: 'Same community/village',
  CTX_co_resident: 'Co-resident in some panel year',
  CTX_same_region: 'Same broad region',
}

const DEFAULT_WEIGHTS = () => ({
  paternal_lineage_proximity: 1.0,
  shared_siblings: 1.0,
  same_household_history: 1.0,
  same_banner: 1.0,
})
const DEFAULT_MOTIFS = () => Object.fromEntries(MOTIF_IDS.map(id => [id, true]))

const state = reactive({
  weights: DEFAULT_WEIGHTS(),
  motifs_enabled: DEFAULT_MOTIFS(),
})

const HUSBAND_PREFIX = 'cmgpd-cell-rules-husband-'

function loadFor(husband_id) {
  // In readonly (transfer) mode the source of truth is the bound cell
  // profile, not the per-husband localStorage sheet. Skip the reset so we
  // don't briefly flash defaults before the cell-rules-updated event lands.
  if (props.readonly) return
  Object.assign(state.weights, DEFAULT_WEIGHTS())
  Object.assign(state.motifs_enabled, DEFAULT_MOTIFS())
  try {
    const raw = localStorage.getItem(HUSBAND_PREFIX + husband_id)
    if (!raw) return
    const obj = JSON.parse(raw)
    if (obj?.weights) Object.assign(state.weights, obj.weights)
    if (obj?.motifs_enabled) Object.assign(state.motifs_enabled, obj.motifs_enabled)
  } catch {}
}

function loadFromCellProfile({ weights, motifs_enabled }) {
  if (weights) Object.assign(state.weights, weights)
  if (motifs_enabled) {
    // Motifs not present in the saved profile keep the editor's default (true).
    for (const k of Object.keys(motifs_enabled)) {
      state.motifs_enabled[k] = !!motifs_enabled[k]
    }
  }
}

let saveTimer = null
function persist() {
  if (props.readonly || !props.husband?.husband_id) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(
        HUSBAND_PREFIX + props.husband.husband_id,
        JSON.stringify({ weights: { ...state.weights }, motifs_enabled: { ...state.motifs_enabled } }),
      )
    } catch {}
  }, 200)
}

function onChange() {
  persist()
  bus.emit('cell-rules-updated', {
    husband_id: props.husband?.husband_id,
    weights: { ...state.weights },
    motifs_enabled: { ...state.motifs_enabled },
  })
}

// In transfer mode (1885+), read the cell-bound profile pushed by F2.
function onCellRulesFromV6(payload) {
  if (!props.readonly) return
  loadFromCellProfile(payload || {})
}

watch(() => props.husband?.husband_id, (hid) => {
  if (hid) loadFor(hid)
}, { immediate: true })

import { onMounted, onUnmounted } from 'vue'
onMounted(() => bus.on('cell-rules-updated', onCellRulesFromV6))
onUnmounted(() => bus.off('cell-rules-updated', onCellRulesFromV6))
</script>

<style scoped lang="less">
.rwe {
  border-top: 1px dashed #d4c8a3;
  padding: 6px 4px 4px;
  display: flex; flex-direction: column; gap: 4px;
}
.rwe.readonly { opacity: 0.85; background: #f9f4e6; }
.empty { color: #888; font-size: 11px; font-style: italic; padding: 8px; }
.weights-grid {
  display: grid;
  grid-template-columns: 70px 1fr 36px 70px 1fr 36px;
  gap: 3px 6px; align-items: center;
}
.weight-row {
  display: contents;
}
.weight-row .lbl { color: #1a1a1a; font-size: 10px; }
.weight-row .slider { width: 100%; height: 12px; }
.weight-row .val { text-align: right; color: #555; font-variant-numeric: tabular-nums; }

.motif-grid {
  display: flex; flex-wrap: wrap; gap: 3px 6px; align-items: center;
  padding: 4px 0 0 0;
}
.motif-head { width: 100%; }
.motif-chk {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10px; padding: 1px 5px;
  border: 1px solid #aaa; border-radius: 3px;
  background: #f5f5f5; color: #1a1a1a; cursor: pointer; user-select: none;
  &.on { background: #ffe082; border-color: #d4a85d; font-weight: 600; }
  & > input { margin: 0; cursor: pointer; }
}
.ro-banner { padding-top: 2px; color: #6b5736; }
</style>
