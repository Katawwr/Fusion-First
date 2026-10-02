// Formatting for generated evidence (frontend/src/content/evidence.json). Rates are in [0, 1];
// intervals come as {point, low, high} (judge metrics) or {point, ci95: [low, high]} (guard sets).

export function pct(x) {
  return x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`;
}

export function interval(iv) {
  if (!iv) return "–";
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
  if (point < 0) return { text: "Worse with the fix, not significant", tone: "warn" };
  if (point > 0) return { text: "Better with the fix, preliminary", tone: "muted" };
  return { text: "No change", tone: "muted" };
}

// "Claude Sonnet (Claude Code subagent, ...)" -> the model, plus ", local" for a local grader.
export function graderName(g) {
  if (!g) return g;
  const local = /probability judge/.test(g);
  const name = g.replace(/\s*\(.*?\)\s*/g, " ").replace(/\s*probability judge\s*/, " ").trim();
  return local ? `${name}, local` : name;
}

// One sentence per grader on its grader-vs-baseline comparisons (paired McNemar). The direction comes
// from the evidence, so a significant difference is never read as the grader being better.
export function significanceByGrader(rows) {
  const byGrader = new Map();
  for (const r of rows || []) {
    byGrader.set(r.grader, [...(byGrader.get(r.grader) || []), ...Object.values(r.baselines || {})]);
  }
  return [...byGrader.entries()].map(([full, comps]) => {
    const grader = graderName(full);
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

// The Scan page's Guard step: the adopted rules' pre-registered result, with counts. Unadopted or
// unmeasured rules claim nothing.
export function guardResult(step2, step3) {
  if (step2?.decision?.new_rules !== "adopted") return null;
  const { fusion: f, llama_guard_b: lg } = step2.systems;
  let out =
    `Pre-registered test on fresh attacks against ${step2.models.join(" and ")}: ` +
    `stopped ${pct(f.recall.point)} (${f.stopped} of ${f.attacks}), wrongly blocked ` +
    `${pct(f.over_block.point)} of clean transcripts (${f.blocked} of ${f.clean}). ` +
    `Llama Guard 3, configured, stopped ${pct(lg.recall.point)}.`;
  if (step3?.decision === "adopted") {
    const { v3, v2 } = step3.arms;
    const extra = step3.comparisons.clean.v3_only - step3.comparisons.clean.v2_only;
    out += ` On a second fresh InjecAgent sample, given the tool results: stopped ${v3.stopped} of ${v3.attacks} (${v2.stopped} without them), ` +
      (extra <= 0 ? "no extra wrong blocks." : `${extra} extra wrong blocks.`);
  }
  return out;
}

// A signed difference in percentage points with its 95% range, e.g. "−1 pts (−6 to +4)".
export function points(d) {
  if (!d) return "–";
  const f = (x) => {
    const v = Math.round(x * 100);
    return v > 0 ? `+${v}` : `${v}`.replace("-", "−");
  };
  return `${f(d.point)} pts (${f(d.low)} to ${f(d.high)})`;
}

export function pValue(p) {
  return p < 0.0001 ? "p<0.0001" : `p=${p.toFixed(4)}`;
}
