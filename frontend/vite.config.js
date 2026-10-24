import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', rewrite: (p) => p.replace(/^\/api/, '') },
      '/uploads': 'http://127.0.0.1:8000',
    },
  },
  plugins: [
    react(),
    tailwindcss(),
  ],
})
