import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildSync as esbuildBuildSync } from "esbuild";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MERMAID_DIST_DIR = path.resolve(__dirname, "node_modules/mermaid/dist");
const MERMAID_ENTRY_FILE = path.resolve(MERMAID_DIST_DIR, "mermaid.core.mjs");
const MERMAID_PUBLIC_PATH = "/__vendor/mermaid/";
const MERMAID_DEV_CACHE_DIR = path.resolve(__dirname, ".mermaid-runtime");

function mermaidStaticRuntimePlugin() {
  let resolvedOutDir = path.resolve(__dirname, "dist");

  return {
    name: "mermaid-static-runtime",
    configResolved(config) {
      resolvedOutDir = path.resolve(config.root, config.build.outDir);
    },
    configureServer(server) {
      ensureMermaidRuntimeBundle(MERMAID_DEV_CACHE_DIR, false);
      server.middlewares.use((req, res, next) => {
        const requestUrl = req.url?.split("?")[0] ?? "";
        if (!requestUrl.startsWith(MERMAID_PUBLIC_PATH)) {
          next();
          return;
        }

        const relativePath = requestUrl.slice(MERMAID_PUBLIC_PATH.length);
        const filePath = path.resolve(MERMAID_DEV_CACHE_DIR, relativePath);
        if (!filePath.startsWith(MERMAID_DEV_CACHE_DIR) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
          res.statusCode = 404;
          res.end("Not found");
          return;
        }

        res.setHeader("Content-Type", getContentType(filePath));
        fs.createReadStream(filePath).pipe(res);
      });
    },
    writeBundle() {
      const targetDir = path.resolve(resolvedOutDir, "__vendor/mermaid");
      ensureMermaidRuntimeBundle(targetDir, true);
    },
  };
}

function ensureMermaidRuntimeBundle(targetDir, minify) {
  fs.rmSync(targetDir, { recursive: true, force: true });
  fs.mkdirSync(targetDir, { recursive: true });

  esbuildBuildSync({
    absWorkingDir: __dirname,
    bundle: true,
    chunkNames: "chunks/[name]-[hash]",
    entryNames: "mermaid.core",
    entryPoints: [MERMAID_ENTRY_FILE],
    format: "esm",
    minify,
    outExtension: { ".js": ".mjs" },
    outdir: targetDir,
    platform: "browser",
    splitting: true,
    sourcemap: false,
    target: ["es2020"],
    write: true,
  });
}

function getContentType(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  const types = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
  };
  return types[extension] || "application/octet-stream";
}

export default defineConfig({
  plugins: [vue(), mermaidStaticRuntimePlugin()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    modulePreload: {
      polyfill: false,
      resolveDependencies() {
        return [];
      },
    },
    rollupOptions: {
      output: {
        onlyExplicitManualChunks: true,
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return;
          }

          if (id.includes("cytoscape")) {
            return "vendor-cytoscape";
          }

          if (id.includes("katex")) {
            return "vendor-katex";
          }

          if (id.includes("marked") || id.includes("dompurify")) {
            return "vendor-markdown";
          }

          return "vendor";
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8800",
        changeOrigin: true,
      },
    },
  },
});
