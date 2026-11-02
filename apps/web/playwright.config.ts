import { existsSync, readFileSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

// O .env.local do app web (URL e chave pública da stack local) vale também para os testes e para a
// API que eles sobem; no CI as variáveis já vêm do ambiente.
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const [key, ...value] = line.split("=");
    if (key && value.length > 0 && !(key in process.env)) process.env[key] = value.join("=");
  }
}

// Exige a stack local (`supabase start`), o .env.local do app web e o `uv` para subir a API.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  // Snapshots sem o nome do sistema: o CI e a máquina local rodam o mesmo Chromium no Linux.
  snapshotPathTemplate: "{testDir}/__screenshots__/{testFilePath}/{projectName}/{arg}{ext}",
  projects: [
    { name: "mobile-chrome", use: { ...devices["Pixel 7"] } },
    // No desktop, só o que muda de layout: o resto dos fluxos é igual.
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testMatch: /shell\.spec\.ts/ },
  ],
  webServer: [
    {
      command: "pnpm build && pnpm start --hostname 127.0.0.1",
      url: "http://127.0.0.1:3000/login",
      timeout: 180_000,
      reuseExistingServer: true,
      env: { COMPONENT_CATALOG: "1" },
    },
    {
      command: "uv run uvicorn aid_api.main:app --host 127.0.0.1 --port 8000",
      cwd: "../..",
      url: "http://127.0.0.1:8000/api/v1/openapi.json",
      timeout: 60_000,
      reuseExistingServer: true,
      env: {
        SUPABASE_DB_URL: "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        SUPABASE_JWT_ISSUER: "http://127.0.0.1:54321/auth/v1",
        SMTP_URL: "smtp://127.0.0.1:54325",
        SUPABASE_URL: "http://127.0.0.1:54321",
        SUPABASE_PUBLISHABLE_KEY: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "",
        APP_URL: "http://127.0.0.1:3000",
      },
    },
  ],
});
