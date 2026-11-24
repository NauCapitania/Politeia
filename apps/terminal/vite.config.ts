/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/v1': { target: process.env.POLITEIA_API ?? 'http://localhost:8000', changeOrigin: true },
      '/api': { target: process.env.POLITEIA_AGENTE ?? 'http://localhost:8788' },
    },
  },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], css: false },
})
