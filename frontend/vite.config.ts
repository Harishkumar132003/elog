import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const PORT = 7205
/** Where the dev proxy forwards /api. Only used when VITE_API_URL is unset. */
const BACKEND = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:7200'

export default defineConfig({
  plugins: [react()],
  server: {
    port: PORT,
    // Fail loudly if 7205 is taken instead of drifting to 7206. A moved port
    // silently breaks the backend's CORS allow-list and the .env the browser
    // was built with, which is a confusing way to find out.
    strictPort: true,
    // Kept even though VITE_API_URL can point straight at the backend: with the
    // variable unset, requests stay relative and come through here, so dev needs
    // no CORS at all.
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
    },
  },
  // `vite preview` serves the built bundle; same port so the URL never changes.
  preview: {
    port: PORT,
    strictPort: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    target: 'es2020',
    cssCodeSplit: true,
  },
})
