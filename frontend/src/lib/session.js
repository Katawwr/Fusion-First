// The last scan, kept in sessionStorage so a refresh doesn't lose the report. Storage can be blocked
// or full (private windows, previews): reads fall back to an empty scan and writes fail silently.

const KEY = "fusion.scan";
export const EMPTY_SCAN = { systemPrompt: "", result: null, scanId: null };

export function loadScanState() {
  try {
    const raw = sessionStorage.getItem(KEY);
    const value = raw ? JSON.parse(raw) : null;
    return value && typeof value === "object" ? { ...EMPTY_SCAN, ...value } : EMPTY_SCAN;
  } catch {
    return EMPTY_SCAN;
  }
}

export function saveScanState(state) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // storage unavailable: the scan still works, it just won't survive a refresh
  }
}
