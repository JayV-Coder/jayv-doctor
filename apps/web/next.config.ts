import type { NextConfig } from "next";

// Identifica o build no registro do service worker: mudou o build, o navegador instala um novo.
const BUILD_ID = process.env.GIT_SHA ?? Date.now().toString(36);

const config: NextConfig = {
  poweredByHeader: false,
  env: { NEXT_PUBLIC_BUILD_ID: BUILD_ID },
  // Navegadores e ferramentas pedem /favicon.ico mesmo com o <link rel="icon"> no <head>.
  rewrites() {
    return Promise.resolve([{ source: "/favicon.ico", destination: "/icons/icon-192.png" }]);
  },
  // O navegador precisa buscar o service worker novo a cada deploy.
  headers() {
    return Promise.resolve([
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self'" },
        ],
      },
    ]);
  },
};

export default config;
