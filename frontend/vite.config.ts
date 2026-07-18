import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load from frontend/ first, then monorepo root — never prefer an empty override.
  const localEnv = loadEnv(mode, __dirname, '');
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '..'), '');

  const mapsKey =
    localEnv.VITE_GOOGLE_MAPS_API_KEY ||
    localEnv.VITE_GOOGLE_MAPS_PLATFORM_KEY ||
    rootEnv.VITE_GOOGLE_MAPS_API_KEY ||
    rootEnv.GOOGLE_MAPS_BROWSER_API_KEY ||
    rootEnv.GOOGLE_MAPS_PLATFORM_KEY ||
    '';

  const mapId =
    localEnv.VITE_GOOGLE_MAPS_MAP_ID ||
    rootEnv.VITE_GOOGLE_MAPS_MAP_ID ||
    '';

  const define: Record<string, string> = {
    'process.env.APP_URL': JSON.stringify(localEnv.APP_URL || rootEnv.APP_URL || ''),
  };

  // Only inject maps keys when non-empty so we never wipe frontend/.env with "".
  if (mapsKey) {
    define['import.meta.env.VITE_GOOGLE_MAPS_API_KEY'] = JSON.stringify(mapsKey);
    define['import.meta.env.VITE_GOOGLE_MAPS_PLATFORM_KEY'] = JSON.stringify(mapsKey);
    define['process.env.GOOGLE_MAPS_PLATFORM_KEY'] = JSON.stringify(mapsKey);
  }
  if (mapId) {
    define['import.meta.env.VITE_GOOGLE_MAPS_MAP_ID'] = JSON.stringify(mapId);
  }

  if (!mapsKey) {
    console.warn(
      '[vite] Google Maps API key not found. Set VITE_GOOGLE_MAPS_API_KEY in frontend/.env ' +
        'or GOOGLE_MAPS_BROWSER_API_KEY in the project root .env (UTF-8 without BOM).',
    );
  } else {
    console.info(`[vite] Google Maps key loaded (len=${mapsKey.length})`);
  }

  return {
    // Relative asset URLs so `npm run preview` and static hosts under a subpath work.
    // Absolute `/assets/...` breaks when opening dist incorrectly or from a nested path.
    base: './',
    plugins: [react(), tailwindcss()],
    define,
    envDir: __dirname,
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8010',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
        },
      },
    },
    preview: {
      port: 4173,
      // Proxy API in preview the same way as dev, so production build can talk to backend
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8010',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
        },
      },
    },
  };
});

