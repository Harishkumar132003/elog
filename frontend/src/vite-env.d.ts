/// <reference types="vite/client" />

/** The VITE_* variables this app reads. Declared so a typo is a type error
 *  rather than a silent `undefined` at runtime. */
interface ImportMetaEnv {
  /** Backend origin, e.g. `http://localhost:7200`. Empty uses the dev proxy. */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
