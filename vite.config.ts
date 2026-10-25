import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const { BACKEND_TARGET = 'http://127.0.0.1:8000' } = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [
      react(),
      tailwindcss(),
    ],
    server: {
      port: 5173,
      proxy: Object.fromEntries(
        ['/upload', '/process', '/status', '/download', '/outputs', '/health', '/parse-preview', '/chat-preview']
          .map(path => [path, BACKEND_TARGET]),
      ),
    },
  }
})
