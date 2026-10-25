import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/upload': 'http://127.0.0.1:8000',
      '/process': 'http://127.0.0.1:8000',
      '/status': 'http://127.0.0.1:8000',
      '/download': 'http://127.0.0.1:8000',
      '/outputs': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/parse-preview': 'http://127.0.0.1:8000',
      '/chat-preview': 'http://127.0.0.1:8000',
    }
  }
})
