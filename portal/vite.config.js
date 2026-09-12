import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/portal/',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/sentinelx': 'http://localhost:8080',
      '/gateway': 'http://localhost:8080',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
