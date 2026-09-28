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

// One sentence per grader on its grader-vs-baseline comparisons (paired McNemar). The direction comes
// from the evidence, so a significant difference is never read as the grader being better.
export function significanceByGrader(rows) {
  const byGrader = new Map();
  for (const r of rows || []) {
    byGrader.set(r.grader, [...(byGrader.get(r.grader) || []), ...Object.values(r.baselines || {})]);
  }
  return [...byGrader.entries()].map(([grader, comps]) => {
    const better = comps.filter((c) => c.mcnemar_p < 0.05 && c.grader_more_accurate).length;
    const worse = comps.filter((c) => c.mcnemar_p < 0.05 && !c.grader_more_accurate).length;
    const n = comps.length;
    if (better && worse)
      return `${grader}: significantly more accurate in ${better} and less accurate in ${worse} of ${n} comparisons with rule-based checks.`;
    if (worse) return `${grader}: significantly less accurate than a rule-based check in ${worse} of ${n} comparisons.`;
    if (better) return `${grader}: significantly more accurate than a rule-based check in ${better} of ${n} comparisons.`;
    return comps.every((c) => c.grader_more_accurate)
      ? `${grader}: scores higher than the rule-based checks; no difference is significant yet.`
      : `${grader}: no difference from the rule-based checks is significant yet.`;
  });
}

// The landing page's guardrail sentence. Its numbers come from the generated evidence (the
// pre-registered measurement on real attacks), never from the page source; unmeasured, it claims none.
// The current rules' measurement (step 2) is preferred once adopted.
export function guardrailDescription(runtime, step2) {
  const base =
    "A hardened system prompt, re-tested on your model. On the small open-weight models we measured, it rarely cut attacks and raised refusals of safe requests. A runtime guardrail redacts leaked secrets and blocks tool calls the user's request does not cover.";
  if (step2?.decision?.new_rules === "adopted") {
    const s = step2.systems;
    return (
      `${base} On fresh attacks against ${step2.models.join(" and ")}, the guardrail stopped ` +
      `${pct(s.fusion.recall.point)} and wrongly blocked ${pct(s.fusion.over_block.point)} of clean conversations; ` +
      `Llama Guard 3 stopped ${pct(s.llama_guard_b.recall.point)} of the same attacks.`
    );
  }
  if (!runtime?.all) return base;
  return (
    `${base} On ${runtime.fresh ? "fresh " : ""}attacks that got through those models, the guardrail stopped ` +
    `${pct(runtime.all.recall.point)} and wrongly blocked ${pct(runtime.all.over_block.point)} of clean conversations.`
  );
}
