// Client for the new Fusion Safety API (the fusion-safety-api Modal app).
// Ported from the legacy SSE fetch+getReader reader; targets VITE_API_URL.

export const API_URL =
  import.meta.env.VITE_API_URL ||
  'https://katawwr--fusion-quality-tester-fastapi-app.modal.run';

// Wake a possibly-cold Modal container so the first real request isn't stuck on cold start.
export async function wakeBackend() {
  try {
    const r = await fetch(`${API_URL}/api/health`);
    return r.ok;
  } catch {
    return false;
  }
}

export async function getScan(scanId) {
  const r = await fetch(`${API_URL}/api/scan/${encodeURIComponent(scanId)}`);
  if (!r.ok) throw new Error(r.status === 404 ? 'Scan not found' : 'Failed to load scan');
  return r.json();
}

export function reportHtmlUrl(scanId) {
  return `${API_URL}/api/scan/${encodeURIComponent(scanId)}/report.html`;
}

export async function harden(systemPrompt, checks = null) {
  const r = await fetch(`${API_URL}/api/harden`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ system_prompt: systemPrompt, checks }),
  });
  if (!r.ok) throw new Error('Failed to harden prompt');
  return r.json();
}

export async function guardrailSnippet(checks = null) {
  const r = await fetch(`${API_URL}/api/guardrail-snippet`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ checks }),
  });
  if (!r.ok) throw new Error('Failed to load guardrail snippet');
  return r.json();
}

// Stream a scan over SSE. `handlers` is an object of callbacks keyed by event name
// (scan_id, scan_started, check_started, probe_result, check_completed, scan_completed, error).
// Returns the final ScanResult (or throws). `signal` (optional) cancels the stream.
export async function streamScan(body, handlers = {}, signal) {
  await wakeBackend();
  const resp = await fetch(`${API_URL}/api/scan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    if (resp.status === 402) throw new Error(text || 'Real scans require an upgrade.');
    throw new Error(text || `Server error: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = null;
  let result = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:') && currentEvent) {
        try {
          const data = JSON.parse(line.slice(5).trim());
          handlers[currentEvent]?.(data);
          if (currentEvent === 'scan_completed') result = data.result;
        } catch {
          /* ignore malformed frame */
        }
        currentEvent = null;
      }
    }
  }
  return result;
}
