import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
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
          target: env.SSAMS_API_TARGET || 'http://127.0.0.1:8000',
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
