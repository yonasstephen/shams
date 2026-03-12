import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Put Vite's dep cache in /tmp to avoid stale-chunk errors when node_modules
  // is baked into the Docker image and the cache gets into an inconsistent state.
  cacheDir: '/tmp/vite',
  server: {
    port: 5173,
    host: true,
  },
})

