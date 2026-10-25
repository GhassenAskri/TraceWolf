import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Carbon's own Sass still uses the `if()` function that Sass is deprecating; nothing to fix here.
  css: { preprocessorOptions: { scss: { silenceDeprecations: ['if-function'] } } },
  // The API allows this origin by default (CORS_ORIGINS), so the port must not drift.
  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true },
})
