import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI backend serves web/dist at "/" and the API at "/api/*" on the same origin,
// so all fetches use relative URLs. In dev, proxy /api to the backend on :8000.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // keep Vite's preload helper out of the (lazy) monaco chunk so the entry never depends on it
          if (id.includes("preload-helper")) return "react";
          if (id.includes("node_modules/three/")) return "three";
          if (id.includes("node_modules/monaco-editor/")) return "monaco";
          if (id.includes("node_modules/react") || id.includes("node_modules/scheduler")) return "react";
        },
      },
    },
  },
});
