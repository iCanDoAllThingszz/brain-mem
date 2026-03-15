import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8100',
      '/logs': 'http://localhost:8100',
      '/hooks': 'http://localhost:8100',
      '/health': 'http://localhost:8100',
    }
  }
})
