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

// The landing page's guardrail sentence. Its numbers come from the generated evidence (the
// pre-registered measurement on real attacks), never from the page source; unmeasured, it claims none.
export function guardrailDescription(runtime) {
  const base =
    "A hardened system prompt, re-tested on your model so you can see whether it actually helps (on the small open-weight models we measured, it rarely cut attacks and made them refuse more safe requests), plus a runtime guardrail that blocks leaked secrets and unauthorized actions even when the model slips.";
  if (!runtime?.all) return base;
  return (
    `${base} On the attacks that really got through those models, the guardrail stopped ` +
    `${pct(runtime.all.recall.point)} of the real attacks, wrongly blocking ` +
    `${pct(runtime.all.over_block.point)} of clean conversations.`
  );
}
