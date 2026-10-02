// Pure Server-Sent Events parser: chunk boundaries anywhere, CRLF or LF, ":" heartbeat lines, multi-line
// data. Calls onEvent(name, data) per complete event; malformed JSON is reported as
// onEvent("parse_error", raw) rather than thrown.

export function createSseParser(onEvent) {
  let buffer = "";
  let eventName = "";
  let dataLines = [];

  function dispatch() {
    if (!dataLines.length) {
      eventName = "";
      return;
    }
    const raw = dataLines.join("\n");
    const name = eventName || "message";
    eventName = "";
    dataLines = [];
    let data;
    try {
      data = JSON.parse(raw);
    } catch {
      onEvent("parse_error", raw);
      return;
    }
    onEvent(name, data);
  }

  function line(l) {
    if (l === "") {
      dispatch();
    } else if (l.startsWith(":")) {
      // comment / heartbeat: ignore
    } else if (l.startsWith("event:")) {
      eventName = l.slice(6).trim();
    } else if (l.startsWith("data:")) {
      dataLines.push(l.slice(5).replace(/^ /, ""));
    }
  }

  return {
    feed(chunk) {
      buffer += chunk;
      const parts = buffer.split(/\r?\n/);
      buffer = parts.pop();
      parts.forEach(line);
    },
    flush() {
      if (buffer) {
        line(buffer);
        buffer = "";
      }
      dispatch();
    },
  };
}
