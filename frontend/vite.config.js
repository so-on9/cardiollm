import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  base: "/static/react/",
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "../proxy/static/react"),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: "ui.js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: (assetInfo) =>
          assetInfo.name?.endsWith(".css")
            ? "ui.css"
            : "assets/[name]-[hash][extname]",
      },
    },
  },
});
