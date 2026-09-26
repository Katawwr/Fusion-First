// Formatting for generated evidence (frontend/src/content/evidence.json). Rates are in [0, 1];
// intervals come as {point, low, high} (judge metrics) or {point, ci95: [low, high]} (guard sets).

export function pct(x) {
  return x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`;
}

export function interval(iv) {
  if (!iv) return "—";
  const low = iv.low ?? iv.ci95?.[0];
  const high = iv.high ?? iv.ci95?.[1];
  return `${pct(iv.point)} (${pct(low)}–${pct(high)})`;
}
