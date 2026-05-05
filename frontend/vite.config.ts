/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Dev-only API proxy. Production builds bake the absolute API URL into
    // the bundle and bypass this entirely. The proxy lets the dev server
    // origin (localhost:517X) make same-origin fetches; Vite forwards them
    // to CloudFront server-side, which sidesteps the API Gateway CORS
    // allow-list (scoped to the production frontend origin only).
    proxy: {
      '/api': {
        target: 'https://d17hrttnkrygh8.cloudfront.net',
        changeOrigin: true,
        secure: true,
      },
      '/scoreboard': {
        target: 'https://d17hrttnkrygh8.cloudfront.net',
        changeOrigin: true,
        secure: true,
      },
      '/games': {
        target: 'https://d17hrttnkrygh8.cloudfront.net',
        changeOrigin: true,
        secure: true,
      },
      '/content': {
        target: 'https://d17hrttnkrygh8.cloudfront.net',
        changeOrigin: true,
        secure: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
