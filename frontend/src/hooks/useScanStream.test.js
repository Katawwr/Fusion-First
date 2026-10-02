import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useScanStream } from "./useScanStream";

function sseResponse(text) {
  const enc = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(enc.encode(text));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const frame = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

function mockFetch(streamText) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) =>
      String(url).includes("/api/health")
        ? new Response("{}", { status: 200 })
        : sseResponse(streamText),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("useScanStream", () => {
  it("runs to completion and calls onCompleted once", async () => {
    const result = { overall_grade: "B", cards: [], outcomes: [], checks: [] };
    mockFetch(
      frame("scan_id", { scan_id: "s1" }) +
        frame("scan_started", { total: 1, demonstration: false, message: "go" }) +
        frame("probe_result", { completed: 1, probe: { check: "c", baseline_issue: null } }) +
        frame("scan_completed", { result }),
    );
    const onCompleted = vi.fn();
    const { result: hook } = renderHook(() => useScanStream());
    await act(() => hook.current.start({}, { onCompleted }));
    expect(onCompleted).toHaveBeenCalledTimes(1);
    expect(hook.current.result).toEqual(result);
    expect(hook.current.running).toBe(false);
    expect(hook.current.demonstration).toBe(false);
    expect(hook.current.lanes.c.unscored).toBe(1); // null baseline = unscored, not "clean"
    expect(hook.current.lanes.c.issues).toBe(0);
  });

  it("surfaces a server error event with its message and code", async () => {
    mockFetch(
      frame("scan_id", { scan_id: "s2" }) +
        frame("error", { code: "quota_exhausted", message: "The usage limit was reached." }),
    );
    const { result: hook } = renderHook(() => useScanStream());
    await act(() => hook.current.start({}));
    expect(hook.current.error).toBe("The usage limit was reached.");
    expect(hook.current.errorCode).toBe("quota_exhausted");
    expect(hook.current.running).toBe(false);
  });

  it("never spins forever when the stream ends without a terminal event", async () => {
    mockFetch(frame("scan_id", { scan_id: "s3" }) + frame("scan_started", { total: 8 }));
    const { result: hook } = renderHook(() => useScanStream());
    await act(() => hook.current.start({}));
    await waitFor(() => expect(hook.current.running).toBe(false));
    expect(hook.current.errorCode).toBe("connection_closed");
    expect(hook.current.error).toMatch(/closed before the scan finished \(ref s3\)/);
  });

  it("does not claim demonstration before the server says so", () => {
    const { result: hook } = renderHook(() => useScanStream());
    expect(hook.current.demonstration).toBeNull();
  });
});
