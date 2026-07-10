import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env variables from the project root (..) where .env is located
  const env = loadEnv(mode, "..", "");

  const mapsKey = env.VITE_GOOGLE_MAPS_API_KEY || env.GOOGLE_MAPS_BROWSER_API_KEY || env.GOOGLE_MAPS_PLATFORM_KEY || "";

  return {
    plugins: [react(), tailwindcss()],
    define: {
      "import.meta.env.VITE_GOOGLE_MAPS_API_KEY": JSON.stringify(mapsKey),
      "import.meta.env.VITE_GOOGLE_MAPS_PLATFORM_KEY": JSON.stringify(mapsKey),
      "process.env.GOOGLE_MAPS_PLATFORM_KEY": JSON.stringify(mapsKey),
      "process.env.APP_URL": JSON.stringify(env.APP_URL || "")
    },
    server: {
      port: 3000,
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8010",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
