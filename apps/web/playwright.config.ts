import { defineConfig, devices } from "@playwright/test";

// Exige a stack local (`supabase start`) e o .env.local do app web.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: "list",
  use: { ...devices["Pixel 7"], baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  webServer: {
    command: "pnpm build && pnpm start --hostname 127.0.0.1",
    url: "http://127.0.0.1:3000/login",
    timeout: 180_000,
    reuseExistingServer: true,
  },
});
