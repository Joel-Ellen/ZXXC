import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.js"],
    include: [
      "src/**/*.{spec,test}.{js,ts}",
      "tests/**/*.{spec,test}.{js,ts}",
    ],
    exclude: ["tests/e2e/**", "dist/**", "node_modules/**"],
    clearMocks: true,
    restoreMocks: true,
  },
});
