import { afterEach, describe, expect, it, vi } from "vitest";

// Which server the app talks to. A page served by `fusion serve` (it carries the launch token) must
// always call its OWN origin, whatever VITE_API_URL the frontend happened to be built with.
async function freshScanApi() {
  vi.resetModules();
  return import("./scanApi");
}

function stubFetch() {
  const f = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", f);
  return f;
}

describe("API origin", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    document.head.innerHTML = "";
  });

  it("a page served by `fusion serve` calls its own origin even if built with VITE_API_URL", async () => {
    vi.stubEnv("VITE_API_URL", "http://localhost:8000");
    document.head.innerHTML = '<meta name="fusion-token" content="abc123">';
    const f = stubFetch();
    const { getScan } = await freshScanApi();
    await getScan("s1");
    expect(f.mock.calls[0][0]).toBe("/api/scan/s1");
  });

  it("any other page keeps using VITE_API_URL (hosted deploys)", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com");
    const f = stubFetch();
    const { getScan } = await freshScanApi();
    await getScan("s1");
    expect(f.mock.calls[0][0]).toBe("https://api.example.com/api/scan/s1");
  });
});

describe("downloadReportHtml", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete document.documentElement.dataset.theme;
  });

  async function themeSent(theme) {
    if (theme) document.documentElement.dataset.theme = theme;
    const f = stubFetch();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    URL.createObjectURL = vi.fn(() => "blob:r");
    URL.revokeObjectURL = vi.fn();
    const { downloadReportHtml } = await freshScanApi();
    await downloadReportHtml({ cards: [] });
    return new URL(f.mock.calls[0][0], "http://x").searchParams.get("theme");
  }

  it("sends the theme the user picked on the site", async () => {
    expect(await themeSent("light")).toBe("light");
    expect(await themeSent("dark")).toBe("dark");
  });

  it("sends no theme when the site follows the system, so the report does too", async () => {
    expect(await themeSent(null)).toBeNull();
  });
});
