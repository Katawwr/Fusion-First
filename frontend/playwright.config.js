import { defineConfig, devices } from "@playwright/test";

// End-to-end tests drive the real product: `fusion serve` serving the BUILT frontend (run
// `npm run build` first) behind its locks. FUSION_OFFLINE=1 keeps every run free and deterministic:
// no model is ever called, and live backends report themselves unavailable.
// @playwright/test is pinned to 1.58.2, whose Chromium (revision 1208) is already cached — no download.
const PORT = 8799;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  webServer: {
    command: `python -m fusion_first.cli serve --no-open --port ${PORT} --dist frontend/dist`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/health`,
    env: { FUSION_OFFLINE: "1" },
    reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, grepInvert: /@phone/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, grep: /@phone/ },
  ],
});
