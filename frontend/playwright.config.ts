import { defineConfig, devices } from "@playwright/test";

/**
 * Runs against the FastAPI server, which serves the built bundle from the same
 * origin it will be served from in production. Build first, then start it:
 *
 *   npm run build
 *   ../.venv/Scripts/python.exe -m uvicorn backend.app.main:app --port 8000
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.FIXPROOF_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
