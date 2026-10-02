import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, detailText, errorFromResponse } from "./http";

const resp = (status, body) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("detailText", () => {
  it("reads string, list and coded details", () => {
    expect(detailText({ detail: "nope" }).text).toBe("nope");
    expect(detailText({ detail: [{ msg: "a" }, { msg: "b" }] }).text).toBe("a; b");
    expect(detailText({ detail: { code: "quota_exhausted", message: "limit" } })).toEqual({
      text: "limit",
      code: "quota_exhausted",
    });
    expect(detailText(null).text).toBe("");
  });
});

describe("errorFromResponse", () => {
  it("gives a friendly sentence, never raw JSON", async () => {
    const e = await errorFromResponse(resp(402, { detail: "local backends are off" }));
    expect(e).toBeInstanceOf(ApiError);
    expect(e.status).toBe(402);
    expect(e.message).toMatch(/Live scans aren't available/);
    expect(e.message).not.toMatch(/[{}]/);
  });

  it("maps 5xx and keeps the machine code", async () => {
    const e = await errorFromResponse(resp(502, { detail: { code: "backend_unavailable", message: "stopped" } }));
    expect(e.message).toMatch(/server hit a problem/);
    expect(e.code).toBe("backend_unavailable");
  });
});

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns a network failure into a clear error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiFetch("/api/x")).rejects.toMatchObject({ code: "network" });
  });

  it("rethrows aborts untouched", async () => {
    const abort = Object.assign(new Error("aborted"), { name: "AbortError" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort));
    await expect(apiFetch("/api/x")).rejects.toBe(abort);
  });
});

// `fusion serve` puts a per-launch token in the page; its API refuses writes without it.
describe("launch token", () => {
  const sentHeaders = (fetchMock) => new Headers(fetchMock.mock.calls[0][1].headers);
  const okFetch = () => vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));

  afterEach(() => {
    vi.unstubAllGlobals();
    document.head.innerHTML = "";
  });

  it("sends the page's token to its own API and keeps the other headers", async () => {
    document.head.innerHTML = '<meta name="fusion-token" content="abc123">';
    const f = okFetch();
    vi.stubGlobal("fetch", f);
    await apiFetch("/api/harden", { method: "POST", headers: { "Content-Type": "application/json" } });
    expect(sentHeaders(f).get("X-Fusion-Token")).toBe("abc123");
    expect(sentHeaders(f).get("Content-Type")).toBe("application/json");
  });

  it.each(["https://api.example.com/api/harden", "//api.example.com/api/harden"])(
    "never sends the token to another origin (%s)",
    async (url) => {
      document.head.innerHTML = '<meta name="fusion-token" content="abc123">';
      const f = okFetch();
      vi.stubGlobal("fetch", f);
      await apiFetch(url, { method: "POST" });
      expect(sentHeaders(f).get("X-Fusion-Token")).toBeNull();
    },
  );

  it("adds nothing when the page has no token (hosted site, dev server)", async () => {
    const f = okFetch();
    vi.stubGlobal("fetch", f);
    await apiFetch("/api/harden", { method: "POST" });
    expect(sentHeaders(f).get("X-Fusion-Token")).toBeNull();
  });
});
