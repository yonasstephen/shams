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

// Vite serves HTTPS because the backend must: Yahoo requires an HTTPS OAuth
// redirect_uri, and Chrome's schemeful same-site counts http://localhost and
// https://localhost as different sites. A session cookie set by the HTTPS
// backend is therefore withheld from an HTTP page's XHR, /api/auth/me answers
// 401, and login loops back to the login page forever. Same scheme on both
// sides makes them same-site, which SameSite=Lax already allows.
//
// Falls back to HTTP when no certs are present so a bare `npm run dev` still
// works; generate them with mkcert if you need the OAuth flow.
function httpsConfig() {
  for (const dir of ['/app/certs', path.resolve(__dirname, '../certs')]) {
    const key = path.join(dir, 'key.pem')
    const cert = path.join(dir, 'cert.pem')
    if (fs.existsSync(key) && fs.existsSync(cert)) {
      return { key: fs.readFileSync(key), cert: fs.readFileSync(cert) }
    }
  }
  return undefined
}

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
    https: httpsConfig(),
  },
})

