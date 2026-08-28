import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/v1": {
        target:
          process.env.VITE_SOVEREIGN_DEV_PROXY ??
          "http://127.0.0.1:5175",
      },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
