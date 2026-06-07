import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: proxy data + audio to the FastAPI backend so the SPA uses same-origin
// paths in both dev and the built (FastAPI-served) app.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:7777',
      '/audio': 'http://localhost:7777',
    },
  },
})
