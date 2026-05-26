import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to all interfaces (0.0.0.0) so WSL2 / VM / remote setups can
    // reach the dev server from the host browser. Localhost-only binding
    // sometimes silently fails on WSL2 + Windows browser combinations.
    host: true,
    port: 5174,
  },
})
