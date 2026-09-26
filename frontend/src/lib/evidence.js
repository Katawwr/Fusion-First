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

// What a fix-efficacy cell shows, in words. The honesty badge only describes REDUCTIONS, so a
// statistically significant regression must be named as one rather than shown as "INCONCLUSIVE".
export function fixVerdict(cell) {
  const ba = cell.before_after || {};
  const point = ba.absolute_reduction?.point ?? 0;
  const p = ba.mcnemar_p ?? 1;
  if (point < 0 && p < 0.05) return { text: "Significantly worse with the fix", tone: "danger" };
  if (point > 0 && ba.honesty === "PROVEN") return { text: "Significantly better with the fix", tone: "ok" };
  if (point < 0) return { text: "Worse with the fix (not significant)", tone: "warn" };
  if (point > 0) return { text: `Better with the fix, not proven (${ba.honesty || "—"})`, tone: "muted" };
  return { text: "No change", tone: "muted" };
}
