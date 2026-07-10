import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  return {
  plugins: [react()],
  // The browser-restricted Maps key is intentionally made available to the
  // Maps JavaScript SDK. Keep server-side keys out of this definition.
  define: {
    "import.meta.env.VITE_GOOGLE_MAPS_API_KEY": JSON.stringify(
      env.VITE_GOOGLE_MAPS_API_KEY || env.GOOGLE_MAPS_BROWSER_API_KEY || ""
    ),
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  };
})
