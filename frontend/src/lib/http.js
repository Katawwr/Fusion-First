// One place that turns HTTP failures into friendly, typed errors: never raw JSON on screen.

export class ApiError extends Error {
  constructor(message, { status = 0, code = "", detail = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

const FRIENDLY = {
  402: "Live scans aren't available on this server.",
  403: "This server doesn't allow that.",
  404: "Not found: it may have expired.",
  413: "That prompt is too long.",
  422: "The request wasn't valid.",
  429: "Too many requests: try again in a moment.",
};

// Extract a human sentence from FastAPI-style bodies: {"detail": "..."} | {"detail": [{msg}]} |
// {"detail": {"code", "message"}}.
export function detailText(body) {
  const d = body && typeof body === "object" ? body.detail : null;
  if (typeof d === "string") return { text: d, code: "" };
  if (Array.isArray(d)) {
    const msgs = d.map((x) => (x && x.msg) || "").filter(Boolean);
    return { text: msgs.join("; "), code: "" };
  }
  if (d && typeof d === "object") return { text: d.message || "", code: d.code || "" };
  return { text: "", code: "" };
}

export async function errorFromResponse(resp) {
  let body = null;
  try {
    body = await resp.json();
  } catch {
    body = null;
  }
  const { text, code } = detailText(body);
  const base =
    FRIENDLY[resp.status] ||
    (resp.status >= 500 ? "The server hit a problem." : `Request failed (${resp.status}).`);
  const message = text ? `${base} ${text}` : base;
  return new ApiError(message, { status: resp.status, code, detail: body });
}

// `fusion serve` injects a per-launch token into the page it serves, and its API refuses any write
// without it: so no other website can drive this machine's models. The token only ever goes to
// the page's own origin.
function launchToken() {
  if (typeof document === "undefined") return "";
  return document.querySelector('meta[name="fusion-token"]')?.getAttribute("content") || "";
}

// True when this page was served by `fusion serve`: its API is then always the page's own origin.
export function servedByFusion() {
  return Boolean(launchToken());
}

function withLaunchToken(url, options) {
  const token = launchToken();
  if (!token || new URL(url, window.location.href).origin !== window.location.origin) return options;
  const headers = new Headers(options.headers || {});
  headers.set("X-Fusion-Token", token);
  return { ...options, headers };
}

export async function apiFetch(url, options = {}) {
  let resp;
  try {
    resp = await fetch(url, withLaunchToken(url, options));
  } catch (e) {
    if (e && e.name === "AbortError") throw e;
    throw new ApiError("Can't reach the Fusion server. Is it running?", {
      code: "network",
    });
  }
  if (!resp.ok) throw await errorFromResponse(resp);
  return resp;
}

export async function apiJson(url, options = {}) {
  const resp = await apiFetch(url, options);
  return resp.json();
}
