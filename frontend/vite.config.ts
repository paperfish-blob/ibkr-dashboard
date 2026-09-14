import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5173,
    strictPort: true,
    // Same-origin in dev, so lib/api.ts can use relative /api paths and needs
    // no CORS on the FastAPI side. In production FastAPI serves this build
    // itself, so the same relative paths keep working unchanged.
    proxy: {
      "/api": "http://localhost:9001",
    },
  },
});
