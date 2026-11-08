import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Mantener Host y Origin del navegador coherentes para CSRF en Django.
    // No reescribir Origin/cookies ni desactivar la protección del backend.
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: false } }
  }
});
