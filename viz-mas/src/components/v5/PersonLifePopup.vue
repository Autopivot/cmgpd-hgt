<template>
  <div v-if="open" class="person-life-popup" @click.self="$emit('close')">
    <div class="popup-card">
      <div class="popup-head">
        <span class="chip">{{ roleLabel }}-{{ shortId }}</span>
        <span v-if="narrative?.birth_year" class="tiny muted">b. {{ narrative.birth_year }}</span>
        <span v-if="profileLine" class="tiny muted">{{ profileLine }}</span>
        <button class="popup-close" @click="$emit('close')" title="close">×</button>
      </div>

      <div class="popup-body">
        <div class="paragraph">
          <div v-if="loadingText" class="tiny muted italic">composing life narrative…</div>
          <p v-else-if="narrativeText" class="narrative">{{ narrativeText }}</p>
          <div v-else class="tiny muted italic">no narrative available</div>
        </div>

        <div class="chart-section">
          <div class="section-head tiny">income trajectory</div>
          <IncomeLifeChart
            :income="narrative?.income || []"
            :birth-year="narrative?.birth_year"
            :cohort-year="cohortYear"
            :height="170"
          />
        </div>

        <div v-if="narrative?.events?.length" class="events-section">
          <div class="section-head tiny" @click="rawOpen = !rawOpen">
            <span class="caret">{{ rawOpen ? '▾' : '▸' }}</span>
            raw event records ({{ narrative.events.length }})
          </div>
          <div v-show="rawOpen" class="events-list">
            <div v-for="ev in narrative.events"
                 :key="ev.year + (ev.event_1 || '') + (ev.event_2 || '')"
                 class="event-pill tiny">
              <b>{{ ev.year }}</b>
              <span>{{ [ev.event_1, ev.event_2].filter(Boolean).join(' / ') || '—' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import IncomeLifeChart from './IncomeLifeChart.vue'
import { getNarrative, getNarrativeText } from '../../api/client.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  person: { type: Object, default: null },     // { id, role?, profile? }
  cohortYear: { type: Number, required: true },
})
const emit = defineEmits(['close'])

const narrative = ref(null)
const narrativeText = ref('')
const loadingText = ref(false)
const rawOpen = ref(false)

const roleLabel = computed(() => {
  if (!props.person?.role) return 'p'
  return props.person.role === 'husband' || props.person.role === 'target' ? 't' : 'c'
})
const shortId = computed(() => {
  const id = props.person?.id ?? ''
  return id.toString().replace(/^P/, '')
})
const profileLine = computed(() => {
  const p = props.person?.profile
  if (!p) return ''
  const parts = []
  if (p.banner_label || p.banner_id != null) parts.push(`bnr ${p.banner_label || p.banner_id}`)
  if (p.community_id != null) parts.push(`com ${p.community_id}`)
  if (p.household_id) parts.push(`hh ${p.household_id}`)
  return parts.join(' · ')
})

async function loadAll() {
  if (!props.person?.id) return
  const id = props.person.id
  const role = props.person.role || null
  // Reset for fresh load
  narrative.value = null
  narrativeText.value = ''
  loadingText.value = true
  try {
    const [n, t] = await Promise.all([
      getNarrative(id, props.cohortYear),
      getNarrativeText(id, props.cohortYear, role),
    ])
    narrative.value = n
    narrativeText.value = t?.narrative || ''
  } finally {
    loadingText.value = false
  }
}

watch(() => [props.open, props.person?.id, props.cohortYear],
  ([isOpen]) => { if (isOpen) loadAll() },
  { immediate: true })

function onKey(e) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped lang="less">
.person-life-popup {
  position: absolute;
  inset: 0;
  background: rgba(20, 20, 20, 0.45);
  display: grid; place-items: center;
  z-index: 60;
}
.popup-card {
  width: min(560px, 92%);
  max-height: 92%;
  background: #fdfaf2;
  border: 1px solid #d4a85d;
  border-radius: 5px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.popup-head {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  background: #f3ecdf; border-bottom: 1px solid #d4a85d;
  .chip {
    background: #1d9e75; color: white;
    padding: 1px 6px; border-radius: 3px;
    font-family: Monaco, monospace; font-size: 11px;
  }
  .popup-close {
    margin-left: auto;
    border: none; background: transparent;
    cursor: pointer; font-size: 16px; line-height: 1;
    color: #555;
    &:hover { color: #993c1d; }
  }
}
.popup-body {
  padding: 8px 12px;
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 10px;
}
.paragraph .narrative {
  font-size: 12px; line-height: 1.45; color: #1a1a1a;
  margin: 0;
}
.italic { font-style: italic; }
.section-head {
  font-size: 10px; color: #444; letter-spacing: 0.4px;
  text-transform: uppercase;
  margin: 0 0 3px 0;
  cursor: default;
  .caret { margin-right: 3px; cursor: pointer; }
}
.chart-section { border-top: 1px dashed #d4c8a3; padding-top: 8px; }
.events-section { border-top: 1px dashed #d4c8a3; padding-top: 8px; }
.events-section .section-head { cursor: pointer; }
.events-list {
  display: flex; flex-wrap: wrap; gap: 4px 6px;
}
.event-pill {
  background: #fff; border: 1px solid #d4c8a3;
  padding: 1px 6px; border-radius: 8px;
  font-size: 10px; color: #333;
  b { color: #6b5736; margin-right: 4px; }
}
</style>
