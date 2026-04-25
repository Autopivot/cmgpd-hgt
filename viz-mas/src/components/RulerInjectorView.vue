<template>
  <div class="panel">
    <div class="panel-head">
      <span>V6 · Rule Injector · Macro × Motifs</span>
      <span class="tiny muted">live tweaks (not yet pushed to backend)</span>
      <button class="fs-btn" @click="bus.emit('full-screen', 'v6')" title="Full screen">⛶</button>
    </div>
    <div class="panel-body">
      <div class="section">
        <h3 class="tiny">Macro feature weights</h3>
        <div v-for="r in rules.macro" :key="r.id" class="slider-row">
          <span class="lbl tiny">{{ r.label }}</span>
          <input type="range" min="0" max="2" step="0.05" v-model.number="r.weight" />
          <span class="val tiny">{{ r.weight.toFixed(2) }}</span>
        </div>
      </div>
      <div class="section">
        <h3 class="tiny">Micro motifs</h3>
        <ul class="motifs">
          <li v-for="m in rules.motifs" :key="m.id">
            <label>
              <input type="checkbox" v-model="m.enabled" />
              <span class="motif-title">{{ m.title }}</span>
              <span class="tiny muted">{{ m.example_count }} examples</span>
            </label>
          </li>
        </ul>
      </div>
      <div class="tiny muted footer">
        Stub: weights are local-only. Connecting them to the live MAS scorer
        is part of the FastAPI backend work (POST /rules/macro, /rules/motifs).
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getRules } from '../api/client.js'
import bus from '../utils/eventbus.js'

const rules = ref({ macro: [], motifs: [] })
onMounted(async () => { rules.value = await getRules() })
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
.motifs li label {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; cursor: pointer;
  padding: 3px 5px; border-radius: 3px;
  &:hover { background: #faf4e6; }
}
.motif-title { flex: 1; }
.footer { margin-top: 8px; }
</style>
