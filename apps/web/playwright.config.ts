import { defineConfig, devices } from "@playwright/test";

// Exige a stack local (`supabase start`), o .env.local do app web e o `uv` para subir a API.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: "list",
  use: { ...devices["Pixel 7"], baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  webServer: [
    {
      command: "pnpm build && pnpm start --hostname 127.0.0.1",
      url: "http://127.0.0.1:3000/login",
      timeout: 180_000,
      reuseExistingServer: true,
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
      },
    },
  ],
});
