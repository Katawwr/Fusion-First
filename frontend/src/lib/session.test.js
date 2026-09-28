import { afterEach, describe, expect, it, vi } from "vitest";
import { EMPTY_SCAN, loadScanState, saveScanState } from "./session";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

describe("scan session", () => {
  it("keeps the last scan across a page refresh", () => {
    const state = { systemPrompt: "You are SupportBot.", result: { checks: ["x"], cards: [] }, scanId: "abc" };
    saveScanState(state);
    expect(loadScanState()).toEqual(state);
  });

  it("starts empty when storage is corrupt or blocked, and never throws", () => {
    sessionStorage.setItem("fusion.scan", "{not json");
    expect(loadScanState()).toEqual(EMPTY_SCAN);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadScanState()).toEqual(EMPTY_SCAN);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => saveScanState({ systemPrompt: "p", result: null, scanId: null })).not.toThrow();
  });
});
