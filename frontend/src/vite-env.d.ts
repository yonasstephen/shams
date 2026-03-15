/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// Runtime configuration (loaded from /config.js at container startup)
interface AppConfig {
  API_URL: string
}

interface Window {
  APP_CONFIG?: AppConfig
}

