<template>
  <div class="panel">
    <div class="panel-head">
      <span>V6: Rules View</span>
      <span class="tiny muted" :class="{ ok: synced }">{{ syncStatus }}</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v6')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body">
      <div class="section">
        <h3 class="tiny">Macro feature weights</h3>
        <div v-for="r in rules.macro" :key="r.id" class="slider-row">
          <span class="lbl tiny">{{ r.label }}</span>
          <input type="range" min="0" max="2" step="0.05" v-model.number="r.weight"
                 @input="onMacroChange" />
          <span class="val tiny">{{ r.weight.toFixed(2) }}</span>
        </div>
      </div>
      <div class="section">
        <h3 class="tiny">Micro motifs</h3>
        <ul class="motifs">
          <li v-for="m in rules.motifs" :key="m.id" :class="{ off: !m.enabled }">
            <label>
              <input type="checkbox" v-model="m.enabled" @change="onMotifChange" />
              <MotifGlyph :example="m.example" :size="78" />
              <div class="motif-text">
                <div class="motif-title">{{ m.title }}</div>
                <div class="tiny muted">{{ m.example_count }} examples</div>
              </div>
            </label>
          </li>
        </ul>
      </div>
      <div class="tiny muted footer">
        Sliders + checkboxes are pushed to the live MAS scorer in real time
        when the FastAPI backend at <code>:8001</code> is reachable.
        Without it, changes are kept in a local cache and still reach V5's
        agent rounds and SHAP waterfall.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getRules, postRules } from '../api/client.js'
import bus from '../utils/eventbus.js'
import MotifGlyph from './MotifGlyph.vue'

const rules = ref({ macro: [], motifs: [] })
const synced = ref(false)
const syncStatus = ref('initialising…')

let pushTimer = null
function schedulePush() {
  // Debounce slider drags — push at most every 200 ms.
  clearTimeout(pushTimer)
  pushTimer = setTimeout(async () => {
    syncStatus.value = 'pushing…'
    const macroBody = {}
    for (const r of rules.value.macro) macroBody[r.id] = r.weight
    const motifBody = {}
    for (const m of rules.value.motifs) motifBody[m.id] = m.enabled
    try {
      await postRules({ macro: macroBody, motifs: motifBody })
      synced.value = true
      syncStatus.value = 'synced'
    } catch {
      synced.value = false
      syncStatus.value = 'local only'
    }
    bus.emit('rules-updated', { macro: macroBody, motifs: motifBody })
  }, 200)
}

function onMacroChange() { schedulePush() }
function onMotifChange() { schedulePush() }

onMounted(async () => {
  const r = await getRules()
  rules.value = r
  syncStatus.value = 'synced'
  synced.value = true
})
</script>

<style lang="less" scoped>
.section { margin-bottom: 10px; }
h3 { font-size: 10px; color: #444; margin-bottom: 4px; letter-spacing: 0.5px; text-transform: uppercase; }
.slider-row {
  display: grid;
  grid-template-columns: 1fr 100px 32px;
  gap: 8px; align-items: center; padding: 2px 0;
}
.slider-row .lbl { color: #1a1a1a; }
.slider-row input[type="range"] { width: 100%; height: 14px; }
.slider-row .val { text-align: right; font-variant-numeric: tabular-nums; }

.motifs { display: flex; flex-direction: column; gap: 4px; }
.motifs li {
  &.off { opacity: 0.45; }
}
.motifs li label {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 8px; align-items: center;
  font-size: 11px; cursor: pointer;
  padding: 4px 6px; border-radius: 3px;
  &:hover { background: #faf4e6; }
}
.motif-text { display: flex; flex-direction: column; }
.motif-title { font-size: 11px; font-weight: 600; color: #1a1a1a; }
.footer { margin-top: 8px; }
.ok { color: #0f6e56 !important; }
code { background: #f0efe9; padding: 0 4px; border-radius: 2px; font-size: 9px; }
</style>
