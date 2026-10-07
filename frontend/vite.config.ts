import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // The repository-root .env is the single source of truth for the application port, so the dev
  // server proxies /api to the same backend the unified (single-port) server uses.
  const rootEnv = loadEnv(mode, path.resolve(process.cwd(), '..'), '');
  const apiTarget = env.SSAMS_API_TARGET || rootEnv.SSAMS_API_TARGET || `http://127.0.0.1:${rootEnv.APP_PORT || 8000}`;
  const keyPath = env.SSAMS_DEV_TLS_KEY;
  const certPath = env.SSAMS_DEV_TLS_CERT;
  const https = keyPath && certPath && fs.existsSync(keyPath) && fs.existsSync(certPath)
    ? { key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) }
    : undefined;
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      https,
      allowedHosts: true,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        },
      },
    },
    preview: { host: '0.0.0.0', port: 4173, allowedHosts: true },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test-setup.ts',
      css: true,
    },
  };
});
