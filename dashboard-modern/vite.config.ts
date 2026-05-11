import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const root = fileURLToPath(new URL('.', import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': resolve(root, 'src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    // Dev-only CORS/TLS fallback. SMART authorize still uses OpenEMR's real
    // issuer; post-auth FHIR/OIDC reads are rewritten to this same-origin proxy.
    proxy: {
      '/apis/default': {
        target: 'https://localhost:9300',
        changeOrigin: true,
        secure: false,
      },
      '/oauth2/default': {
        target: 'https://localhost:9300',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      input: {
        main: resolve(root, 'index.html'),
        launch: resolve(root, 'launch.html'),
      },
    },
  },
})
