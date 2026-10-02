import { defineConfig, devices } from "@playwright/test";

// Drives `fusion serve` serving the BUILT frontend (run `npm run build` first) behind its locks.
// FUSION_OFFLINE=1 keeps runs free and deterministic: no model is called. @playwright/test is pinned
// to 1.58.2, whose Chromium is already cached. A second server runs `--demo-only`, as the hosted demo
// does; tests reach it through DEMO_ONLY_URL.
const PORT = 8799;
const DEMO_ONLY_PORT = 8798;
process.env.DEMO_ONLY_URL = `http://127.0.0.1:${DEMO_ONLY_PORT}`;

const server = (port, flags = "") => ({
  command: `python -m fusion_first.cli serve --no-open --port ${port} --dist frontend/dist${flags}`,
  cwd: "..",
  url: `http://127.0.0.1:${port}/api/health`,
  env: { FUSION_OFFLINE: "1" },
  reuseExistingServer: false,
  timeout: 60_000,
});

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  webServer: [server(PORT), server(DEMO_ONLY_PORT, " --demo-only")],
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, grepInvert: /@phone/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, grep: /@phone/ },
  ],
});
