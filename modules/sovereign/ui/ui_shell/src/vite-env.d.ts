/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Development-only override. Production always uses same-origin `/v1`. */
  readonly VITE_SOVEREIGN_BACKEND_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
