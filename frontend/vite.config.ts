import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const BACKEND_URL = 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Forward API and product-image requests to the FastAPI backend (backend/main.py)
    proxy: {
      '/api': BACKEND_URL,
      '/media': BACKEND_URL,
    },
  },
})
