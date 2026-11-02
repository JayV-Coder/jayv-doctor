import type { NextConfig } from "next";

const config: NextConfig = {
  poweredByHeader: false,
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
