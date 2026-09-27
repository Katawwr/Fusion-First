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
    const { getCapabilities } = await freshScanApi();
    await getCapabilities();
    expect(f.mock.calls[0][0]).toBe("/api/version");
  });

  it("any other page keeps using VITE_API_URL (hosted deploys)", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com");
    const f = stubFetch();
    const { getCapabilities } = await freshScanApi();
    await getCapabilities();
    expect(f.mock.calls[0][0]).toBe("https://api.example.com/api/version");
  });
});
