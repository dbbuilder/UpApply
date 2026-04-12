/// <reference types="vite/client" />

declare const __BUILD_DATE__: string;

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
