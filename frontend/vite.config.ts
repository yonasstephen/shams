import fs from 'fs'
import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

function readVersion(): string {
  for (const p of ['../VERSION', './VERSION']) {
    const resolved = path.resolve(__dirname, p)
    if (fs.existsSync(resolved)) return fs.readFileSync(resolved, 'utf-8').trim()
  }
  return '0.0.0'
}

const version = readVersion()

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  // Put Vite's dep cache in /tmp to avoid stale-chunk errors when node_modules
  // is baked into the Docker image and the cache gets into an inconsistent state.
  cacheDir: '/tmp/vite',
  server: {
    port: 5173,
    host: true,
  },
})

