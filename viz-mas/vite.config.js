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
      // Backend stub at 127.0.0.1:8001 (FastAPI for live HGT inference,
      // not yet implemented). Until it's running, the api/client.js falls
      // back to fetching ./data/cohort_<year>.json directly.
      '/api': { target: 'http://127.0.0.1:8001', ws: true, changeOrigin: true },
    },
  },
})
