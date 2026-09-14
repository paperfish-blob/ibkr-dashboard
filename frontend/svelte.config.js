import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    // Static build, served by FastAPI at / in production. Every route is
    // prerendered (see routes/+layout.ts), so no SPA fallback is needed and
    // deep links resolve without a catch-all route on the Python side.
    adapter: adapter({
      pages: "build",
      assets: "build",
      precompress: false,
      strict: true,
    }),
  },
};

export default config;
