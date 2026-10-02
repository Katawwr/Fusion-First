import { test, expect } from "@playwright/test";

// Console errors and uncaught exceptions fail a test. Web fonts come from Google and may be
// unreachable offline, so those requests are ignored.
function watchErrors(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    if (/fonts\.(googleapis|gstatic)\.com/.test(m.location()?.url || "")) return;
    errors.push(m.text());
  });
  return errors;
}

test.describe("desktop", () => {
  test("the overview shows the results table and leads to the scan", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/");
    await expect(page).toHaveTitle(/Fusion First/);
    await expect(page.getByText("Table 1.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Limitations" })).toBeVisible();
    await page.getByRole("link", { name: "Run Demo", exact: true }).click();
    await expect(page).toHaveURL(/\/scan$/);
    expect(errors).toEqual([]);
  });

  test("run it locally: the overview links straight to the setup on /use", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Run Locally", exact: true }).first().click();
    await expect(page).toHaveURL(/\/use#local$/);
    await expect(page.getByRole("heading", { name: "Run Locally" })).toBeInViewport();
    await expect(page.getByText(/FUSION_ALLOW_API_SPEND=1/).first()).toBeVisible();
  });

  test("a demo scan runs end to end and says it is an example, not a measurement", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/scan");
    await page.getByRole("button", { name: "Support Bot" }).click();
    await page.getByRole("button", { name: "Run Scan" }).click();
    await expect(page.getByText("Your report card")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("heading", { name: "Example Report" })).toBeVisible();
    // The HTML report downloads from the result on the page (no server-side scan lookup).
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download Report" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^fusion-report-.+\.html$/);
    // Guard: the guard snippet and the hardened prompt come back through the token-locked API.
    await page.getByRole("button", { name: "Guard It" }).click();
    await expect(page.getByRole("heading", { name: "Runtime guard" })).toBeVisible();
    await expect(page.getByText(/guard_tool_call/).first()).toBeVisible();
    // The in-sample replay runs on live scans only: demo replies are canned.
    await expect(page.getByText(/in-sample replay needs a live scan/)).toBeVisible();
    await page.getByRole("button", { name: "Before/After" }).click();
    // The fix's before/after: the demo's is labelled an example, never a measurement.
    await expect(page.getByText(/Paired measurement on your model/)).toHaveCount(0);
    await expect(page.getByText(/apples-to-apples measurement/)).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("a finished report survives a page refresh and downloads as JSON", async ({ page }) => {
    await page.goto("/scan");
    await page.getByRole("button", { name: "Support Bot" }).click();
    await page.getByRole("button", { name: "Run Scan" }).click();
    await expect(page.getByText("Your report card")).toBeVisible({ timeout: 20_000 });
    await page.reload();
    await expect(page.getByText("Your report card")).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download JSON" }).click();
    expect((await download).suggestedFilename()).toMatch(/^fusion-report-.+\.json$/);
  });

  test("with nothing to grade with, a local server offers the demo and one setup line", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/scan");
    // FUSION_OFFLINE=1: no claude CLI and no hosted grader, so no live target is listed, none disabled.
    await expect(page.getByText(/^Live scans need a grader:/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Setup", exact: true })).toHaveAttribute("href", "/use#local");
    await expect(page.getByRole("radiogroup", { name: "Target model" }).getByRole("radio")).toHaveCount(1);
    await expect(page.getByRole("radio", { name: /^Demo scan/ })).toBeEnabled();
    await expect(page.getByRole("radio", { disabled: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Quality checks" })).toHaveCount(0);
    await expect(page.getByRole("radiogroup", { name: "Attack set" })).toBeVisible();
    // A server that runs local models shows no install line.
    await expect(page.getByRole("link", { name: "Run Locally", exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("a demo-only server offers the demo alone and one line to run live models locally", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto(`${process.env.DEMO_ONLY_URL}/scan`);
    const link = page.getByRole("link", { name: "Run Locally", exact: true });
    await expect(link).toHaveAttribute("href", "/use#local");
    await expect(page.getByText('pip install "fusion-safety[serve]"')).toBeVisible();
    await expect(page.getByRole("radio", { name: /^Demo scan/ })).toBeEnabled();
    await expect(page.getByRole("radiogroup", { name: "Target model" }).getByRole("radio")).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Quality checks" })).toHaveCount(0);
    await expect(page.getByText(/Live scans need a grader/)).toHaveCount(0);
    // The demo still runs end to end there.
    await page.getByRole("button", { name: "Support Bot" }).click();
    await page.getByRole("button", { name: "Run Scan" }).click();
    await expect(page.getByText("Your report card")).toBeVisible({ timeout: 20_000 });
    expect(errors).toEqual([]);
  });

  test("the trust page shows the measured results", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/trust");
    await expect(page.getByRole("heading", { name: "How far to trust Fusion" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Rubric grading vs one plain question/ })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Given the tool results", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("the local API refuses writes that don't carry the page's launch token", async ({ page }) => {
    await page.goto("/");
    const statuses = await page.evaluate(async () => {
      const init = { method: "POST", body: JSON.stringify({ system_prompt: "You are a bot." }) };
      const json = { "Content-Type": "application/json" };
      const token = document.querySelector('meta[name="fusion-token"]').content;
      const without = await fetch("/api/harden", { ...init, headers: json });
      const withToken = await fetch("/api/harden", { ...init, headers: { ...json, "X-Fusion-Token": token } });
      return [without.status, withToken.status];
    });
    expect(statuses).toEqual([403, 200]);
  });

  test("light and dark themes both render", async ({ page }) => {
    await page.goto("/");
    const html = page.locator("html");
    const background = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    const before = await background();
    await page.getByRole("button", { name: /Switch to (light|dark) mode/ }).click();
    await expect(html).toHaveAttribute("data-theme", /light|dark/);
    expect(await background()).not.toBe(before);
  });
});

// Tagged @phone: only the phone project runs these (see playwright.config.js).
test.describe("phone", () => {
  test("the Trust page charts fit a phone without sideways scrolling @phone", async ({ page }) => {
    await page.goto("/trust");
    await expect(page.getByRole("img", { name: /^Guard trade-off/ })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("no sideways scrolling on the Guard step @phone", async ({ page }) => {
    await page.goto("/scan");
    await page.getByRole("button", { name: "Support Bot" }).click();
    await page.getByRole("button", { name: "Run Scan" }).click();
    await page.getByRole("button", { name: "Guard It" }).click();
    await expect(page.getByRole("button", { name: "Hardened Prompt" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  for (const path of ["/", "/scan", "/trust", "/use"]) {
    test(`no sideways scrolling on ${path} @phone`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
});
