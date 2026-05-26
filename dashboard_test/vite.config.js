import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Mirror dashboard_live: bind to all interfaces so WSL2 / VM / remote
    // hosts can reach the dev server from the host browser. Port stays
    // at Vite's default 5173 (UI lab, distinct from dashboard_live:5174).
    host: true,
  },
})
