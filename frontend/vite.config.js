import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const scraperWorkerUrl = env.VITE_SCRAPER_WORKER_URL || 'http://127.0.0.1:8765'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target: scraperWorkerUrl,
          changeOrigin: true,
          // Adds X-Forwarded-For, so the worker's per-visitor limits see the visitor.
          xfwd: true,
        },
        '/scraper.log': {
          target: scraperWorkerUrl,
          changeOrigin: true,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/setupTests.js'],
    },
  }
})
