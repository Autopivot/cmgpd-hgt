import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5190,
    strictPort: true,
    proxy: {
      // FastAPI backend at 127.0.0.1:8001 (server/main.py). HTTP + WebSocket.
      // If the backend isn't running, viz-mas/src/api/client.js falls back
      // to fetching ./data/cohort_<year>__<ablation>.json directly and
      // simulates the agent stream client-side.
      '/api': { target: 'http://127.0.0.1:8001', ws: true, changeOrigin: true },
    },
  },
})
