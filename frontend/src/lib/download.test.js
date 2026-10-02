import { afterEach, describe, expect, it, vi } from "vitest";
import { downloadJson } from "./download";

afterEach(() => vi.restoreAllMocks());

describe("downloadJson", () => {
  it("saves the value as a named JSON file", async () => {
    URL.createObjectURL = vi.fn(() => "blob:report");
    URL.revokeObjectURL = vi.fn();
    let saved = null;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      saved = { href: this.href, name: this.download };
    });
    downloadJson({ overall_grade: "B" }, "fusion-report.json");
    const blob = URL.createObjectURL.mock.calls[0][0];
    expect(blob.type).toBe("application/json");
    const text = await new Promise((resolve) => {
      const reader = new FileReader(); // jsdom's Blob has no .text()
      reader.onload = () => resolve(reader.result);
      reader.readAsText(blob);
    });
    expect(JSON.parse(text)).toEqual({ overall_grade: "B" });
    expect(saved).toEqual({ href: "blob:report", name: "fusion-report.json" });
    expect(URL.revokeObjectURL).not.toHaveBeenCalled(); // revoking during the click can cancel the download
    await new Promise((r) => setTimeout(r, 1100));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:report");
    expect(document.querySelector("a[download]")).toBeNull();
  });
});
