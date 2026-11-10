// Records the README demo: the offline demo scan on `fusion serve`, from the overview to the report card and
// the guard step. Writes a .webm into the folder given as argv[2].
// Run from frontend/ after `npm run build`: node scripts/record-demo.mjs <out-dir>
// Then: ffmpeg -ss 0.4 -i <out-dir>/<file>.webm -vf "fps=6,scale=800:-1:flags=lanczos,split[a][b];
//   [a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" docs/img/demo.gif
import { spawn } from "node:child_process";
import { chromium } from "@playwright/test";

const PORT = 8797;
const BASE = `http://127.0.0.1:${PORT}`;
const outDir = process.argv[2];
if (!outDir) throw new Error("usage: node scripts/record-demo.mjs <out-dir>");

const server = spawn("python", ["-m", "fusion_first.cli", "serve", "--no-open", "--port", String(PORT),
  "--dist", "frontend/dist"], { cwd: "..", env: { ...process.env, FUSION_OFFLINE: "1" }, stdio: "ignore" });

async function waitForServer() {
  for (let i = 0; i < 120; i += 1) {
    try {
      if ((await fetch(`${BASE}/api/health`)).ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("fusion serve did not start");
}

const pause = (page, ms) => page.waitForTimeout(ms);

try {
  await waitForServer();
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }, colorScheme: "dark",
    recordVideo: { dir: outDir, size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  await page.goto(`${BASE}/`);
  await pause(page, 2200);
  await page.getByRole("link", { name: "Run Demo", exact: true }).click();
  await pause(page, 1200);
  await page.getByRole("button", { name: "Support Bot" }).click();
  await pause(page, 1200);
  await page.getByRole("button", { name: "Run Scan" }).click();
  await page.getByText("Your report card").waitFor({ timeout: 30_000 });
  await page.getByRole("heading", { name: "Example Report" }).evaluate((el) =>
    el.scrollIntoView({ block: "start", behavior: "smooth" }));
  await pause(page, 3200);
  await page.getByRole("button", { name: "Guard It" }).click();
  const guard = page.getByRole("heading", { name: "Runtime guard" });
  await guard.waitFor();
  await guard.evaluate((el) => el.scrollIntoView({ block: "start", behavior: "smooth" }));
  await pause(page, 3800);
  await context.close();
  await browser.close();
} finally {
  server.kill();
}
