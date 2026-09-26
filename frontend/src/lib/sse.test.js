import { describe, expect, it } from "vitest";
import { createSseParser } from "./sse";

function collect(chunks) {
  const events = [];
  const p = createSseParser((name, data) => events.push([name, data]));
  chunks.forEach((c) => p.feed(c));
  p.flush();
  return events;
}

describe("createSseParser", () => {
  it("parses events split across arbitrary chunk boundaries", () => {
    const text = 'event: scan_id\ndata: {"scan_id":"abc"}\n\nevent: error\ndata: {"code":"internal"}\n\n';
    for (let cut = 1; cut < text.length; cut += 7) {
      expect(collect([text.slice(0, cut), text.slice(cut)])).toEqual([
        ["scan_id", { scan_id: "abc" }],
        ["error", { code: "internal" }],
      ]);
    }
  });

  it("handles CRLF line endings", () => {
    expect(collect(['event: x\r\ndata: {"a":1}\r\n\r\n'])).toEqual([["x", { a: 1 }]]);
  });

  it("ignores heartbeat comments", () => {
    expect(collect([': keepalive\n\n', 'event: x\ndata: {"a":2}\n\n'])).toEqual([["x", { a: 2 }]]);
  });

  it("reports malformed JSON instead of throwing", () => {
    expect(collect(["event: x\ndata: {not json\n\n"])).toEqual([["parse_error", "{not json"]]);
  });

  it("dispatches a final event without a trailing blank line on flush", () => {
    expect(collect(['event: scan_completed\ndata: {"result":null}'])).toEqual([
      ["scan_completed", { result: null }],
    ]);
  });
});
