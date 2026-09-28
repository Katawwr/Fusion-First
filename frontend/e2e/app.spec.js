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
  test("the landing page loads and leads to the scan", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/");
    await expect(page).toHaveTitle(/Fusion First/);
    await page.getByRole("link", { name: "Scan your agent", exact: true }).first().click();
    await expect(page).toHaveURL(/\/scan$/);
    expect(errors).toEqual([]);
  });

  test("a demo scan runs end to end and says it is an example, not a measurement", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/scan");
    await page.getByRole("button", { name: "Support bot" }).click();
    await page.getByRole("button", { name: "Run the scan" }).click();
    await expect(page.getByText("Your report card")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Example report — your prompt was not run/)).toBeVisible();
    await expect(page.getByText(/Illustration only/).first()).toBeVisible();
    // Fix: the hardened prompt comes back through the token-locked API.
    await page.getByRole("button", { name: "Fix it" }).click();
    await page.getByRole("button", { name: "See the before/after" }).click();
    // Prove: the demo's before/after is labelled an example, never a measurement.
    await expect(page.getByText(/It is not a measurement/)).toBeVisible();
    await expect(page.getByText(/apples-to-apples measurement/)).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("a finished report survives a page refresh and downloads as JSON", async ({ page }) => {
    await page.goto("/scan");
    await page.getByRole("button", { name: "Support bot" }).click();
    await page.getByRole("button", { name: "Run the scan" }).click();
    await expect(page.getByText("Your report card")).toBeVisible({ timeout: 20_000 });
    await page.reload();
    await expect(page.getByText("Your report card")).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download JSON" }).click();
    expect((await download).suggestedFilename()).toMatch(/^fusion-report-.+\.json$/);
  });

  test("live backends this server can't run are disabled with the reason", async ({ page }) => {
    await page.goto("/scan");
    const claude = page.getByRole("radio", { name: /^Claude/ });
    await expect(claude).toBeDisabled();
    await expect(claude).toContainText(/FUSION_OFFLINE|isn't installed/);
    await expect(page.getByRole("radio", { name: /^Open-weight model/ })).toBeDisabled();
    await expect(page.getByRole("radio", { name: /^Demo scan/ })).toBeEnabled();
  });

  test("the trust page shows the measured results", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/trust");
    await expect(page.getByRole("heading", { name: "How far to trust Fusion" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Rubric judge vs a plain question/ })).toBeVisible();
    await expect(page.getByRole("cell", { name: "v3", exact: true })).toBeVisible();
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
  for (const path of ["/", "/scan", "/trust", "/use"]) {
    test(`no sideways scrolling on ${path} @phone`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
});
