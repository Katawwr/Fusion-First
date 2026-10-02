// Client for the Fusion API (FastAPI + SSE).
// Targets VITE_API_URL when set, else same-origin ('' -> relative /api/... paths), so a misconfigured
// deploy 404s loudly against its own host instead of silently hitting the wrong app. A page served by
// `fusion serve` is always same-origin, whatever the build baked in.
import { saveBlob } from "./download";
import { ApiError, apiFetch, apiJson, servedByFusion } from "./http";
import { createSseParser } from "./sse";

export const API_URL = servedByFusion() ? "" : import.meta.env.VITE_API_URL || "";

const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// Wake a possibly-cold container so the first real request isn't stuck on cold start.
async function wakeBackend() {
  try {
    const r = await fetch(`${API_URL}/api/health`);
    return r.ok;
  } catch {
    return false;
  }
}

export async function getScan(scanId) {
  return apiJson(`${API_URL}/api/scan/${encodeURIComponent(scanId)}`);
}

// The HTML report, rendered by the API from the result the page holds (no server state). It takes the
// theme picked on the site; with none picked it follows the reader's system, as the site does.
export async function downloadReportHtml(result, filename = "fusion-report.html") {
  const picked = document.documentElement.dataset.theme;
  const query = picked === "light" || picked === "dark" ? `?theme=${picked}` : "";
  const resp = await apiFetch(`${API_URL}/api/report.html${query}`, json(result));
  saveBlob(await resp.blob(), filename);
}

export async function harden(systemPrompt, checks = null) {
  return apiJson(`${API_URL}/api/harden`, json({ system_prompt: systemPrompt, checks }));
}

export async function guardrailSnippet(checks = null) {
  return apiJson(`${API_URL}/api/guardrail-snippet`, json({ checks }));
}

// Live-only: needs a real backend on this server.
export async function gradeQuality(systemPrompt, { targetModel = null, backend = null } = {}) {
  return apiJson(
    `${API_URL}/api/grade-quality`,
    json({ system_prompt: systemPrompt, target_model: targetModel, backend }),
  );
}

const TERMINAL = new Set(["scan_completed", "error"]);

// Stream a scan over SSE. `handlers` maps event name → callback (scan_id, scan_started,
// check_started, probe_result, check_completed, scan_completed, error). Contract: the server ends
// every stream with exactly one terminal event (scan_completed | error). If the connection ends
// without one, this throws ApiError(code "connection_closed"): the UI must never spin forever.
export async function streamScan(body, handlers = {}, signal) {
  await wakeBackend();
  const resp = await apiFetch(`${API_URL}/api/scan/stream`, { ...json(body), signal });

  let result = null;
  let terminal = null;
  let scanId = null;
  const parser = createSseParser((name, data) => {
    if (name === "parse_error") return;
    if (name === "scan_id") scanId = data.scan_id;
    if (name === "scan_completed") result = data.result;
    if (TERMINAL.has(name)) terminal = name;
    handlers[name]?.(data);
  });

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.feed(decoder.decode(value, { stream: true }));
  }
  parser.feed(decoder.decode());
  parser.flush();

  if (!terminal) {
    throw new ApiError(
      `The connection closed before the scan finished${scanId ? ` (ref ${scanId})` : ""}.`,
      { code: "connection_closed" },
    );
  }
  return { result, terminal, scanId };
}
