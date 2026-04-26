import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'
import fs from 'node:fs'

// Single-source data: every cohort_<year>__<ablation>.json is served from
// the canonical D:/projects/VIS_2026/NEW/viz/data/ directory. The viz-mas
// app does not maintain a duplicate copy under public/data/. The plugin
// below intercepts /data/* requests during `vite dev` and pipes the file
// out of the canonical location. For `vite build`, run a build step that
// copies (or symlinks) viz/data into viz-mas/public/data first.
const CANONICAL_DATA_DIR = path.resolve(__dirname, '..', 'viz', 'data')

function serveCanonicalData() {
  return {
    name: 'serve-canonical-data',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const rel = decodeURIComponent((req.url || '').replace(/^\//, '').split('?')[0])
        if (!rel || rel.includes('..')) return next()
        const file = path.join(CANONICAL_DATA_DIR, rel)
        if (!fs.existsSync(file) || !fs.statSync(file).isFile()) return next()
        res.setHeader('Content-Type', file.endsWith('.json') ? 'application/json' : 'application/octet-stream')
        res.setHeader('Cache-Control', 'no-store')
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), serveCanonicalData()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5190,
    strictPort: true,
    fs: {
      // Allow vite to read modules from the parent NEW/ tree (viz/, etc.)
      // during dev — required if any import accidentally crosses out of
      // viz-mas/. The /data/ middleware above already short-circuits the
      // common cohort-JSON lookup.
      allow: [path.resolve(__dirname, '..')],
    },
    proxy: {
      // FastAPI backend at 127.0.0.1:8001 (server/main.py). HTTP + WebSocket.
      // If the backend isn't running, viz-mas/src/api/client.js falls back
      // to fetching ./data/cohort_<year>__<ablation>.json from the
      // canonical viz/data/ directory and simulates the agent stream
      // client-side.
      '/api': { target: 'http://127.0.0.1:8001', ws: true, changeOrigin: true },
    },
  },
})
