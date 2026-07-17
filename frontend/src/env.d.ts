/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_SHOW_TEST_ACCOUNTS?: "true" | "false";
  readonly VITE_RESOURCE_GENERATION_ASYNC?: "true" | "false";
  readonly VITE_SENTRY_DSN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
