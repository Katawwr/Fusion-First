// The overview page's results table and findings, built from the generated evidence
// (frontend/src/content/evidence.json). Nothing here carries a number of its own: a block the evidence
// lacks is left out, and a result that was not adopted is not presented as one.
import { pValue } from "./evidence";

const FIX_EXPERIMENTS = {
  injecagent: { label: "Tool hijacks (InjecAgent)", tone: "good" },
  gandalf: { label: "Password leaks (Gandalf)", tone: "good" },
  xstest: { label: "Safe requests refused (XSTest)", tone: "cost" },
  ifeval: { label: "Instructions missed (IFEval)", tone: "cost" },
};

const CHECK_LABELS = {
  direct_prompt_injection: "prompt injection",
  system_prompt_leakage: "system-prompt leakage",
};

const shortGrader = (g) =>
  /^Claude Sonnet/.test(g) ? "Claude Sonnet" : g.replace(/ probability judge \(local\)$/, " (local)");

const count = (k, n) => `${k} of ${n}`;

// Groups of rows: { id, title, note, rows: [{ label, n, est, scale, tone, detail }] }.
// scale "rate" plots on 0–100%; scale "diff" plots a change around zero.
export function resultGroups(ev) {
  const groups = [];

  const s3 = ev.step3_guard;
  if (s3?.decision === "adopted") {
    const v3 = s3.arms.v3;
    const v2 = s3.arms.v2;
    groups.push({
      id: "step3",
      title: "Runtime guard, given the tool results",
      note: `Fresh transcripts of ${s3.models.join(" and ")}; rules ${s3.rules}; adopted.`,
      rows: [
        { label: "Attacks stopped", n: v3.attacks, est: v3.recall, scale: "rate", tone: "good", detail: count(v3.stopped, v3.attacks) },
        { label: "Clean conversations wrongly blocked", n: v3.clean, est: v3.over_block, scale: "rate", tone: "cost", detail: count(v3.blocked, v3.clean) },
        {
          label: "Attacks stopped without the tool results",
          n: v2.attacks,
          est: v2.recall,
          scale: "rate",
          tone: "neutral",
          detail: `${count(v2.stopped, v2.attacks)}; McNemar ${pValue(s3.comparisons.attacks.p)}`,
        },
      ],
    });
  }

  const s2 = ev.step2_guard;
  if (s2?.decision?.new_rules === "adopted") {
    const f = s2.systems.fusion;
    const lg = s2.systems.llama_guard_b;
    groups.push({
      id: "step2",
      title: "Request-bound guard vs Llama Guard 3",
      note: `Fresh transcripts of ${s2.models.join(" and ")}; rules ${s2.rules}; same transcripts for both.`,
      rows: [
        { label: "Fusion guard: attacks stopped", n: f.attacks, est: f.recall, scale: "rate", tone: "good", detail: count(f.stopped, f.attacks) },
        { label: "Fusion guard: clean wrongly blocked", n: f.clean, est: f.over_block, scale: "rate", tone: "cost", detail: count(f.blocked, f.clean) },
        {
          label: "Llama Guard 3, configured: attacks stopped",
          n: lg.attacks,
          est: lg.recall,
          scale: "rate",
          tone: "neutral",
          detail: `${count(lg.stopped, lg.attacks)}; McNemar ${pValue(s2.comparisons.configured.attacks.mcnemar_p)}`,
        },
        { label: "Llama Guard 3, configured: clean wrongly blocked", n: lg.clean, est: lg.over_block, scale: "rate", tone: "neutral", detail: count(lg.blocked, lg.clean) },
      ],
    });
  }

  const judges = (ev.judge_accuracy || []).filter((j) => CHECK_LABELS[j.check]);
  if (judges.length) {
    const floor = ev.local_grader;
    groups.push({
      id: "judge",
      title: "Grader accuracy against deterministic oracles",
      note: "Real transcripts of small open-weight models; oracle labels fixed before grading.",
      rows: judges.map((j) => {
        const below = floor && j.grader === floor.grader && !floor.meets_floor;
        return {
          label: `${shortGrader(j.grader)}, ${CHECK_LABELS[j.check]}`,
          n: j.n,
          est: j.accuracy,
          scale: "rate",
          tone: below ? "neutral" : "good",
          detail: below ? "below the policy floor" : `F1 ${j.f1.toFixed(2)}`,
        };
      }),
    });
  }

  const neg = [];
  const rvp = ev.rubric_vs_plain;
  if (rvp) {
    neg.push({
      label: "Rubric judge minus plain question, accuracy",
      n: rvp.pooled.n,
      est: rvp.pooled.difference,
      scale: "diff",
      tone: "neutral",
      detail: `McNemar ${pValue(rvp.pooled.mcnemar_p)}`,
    });
  }
  for (const p of ev.fix_pooled || []) {
    const meta = FIX_EXPERIMENTS[p.experiment];
    if (!meta) continue;
    neg.push({
      label: `Prompt fix, change in ${meta.label.charAt(0).toLowerCase()}${meta.label.slice(1)}`,
      n: p.n_pairs,
      est: p.change,
      scale: "diff",
      tone: meta.tone,
      detail: p.verdict,
    });
  }
  if (neg.length) {
    groups.push({
      id: "negative",
      title: "Negative results",
      note: `Prompt fix pooled over ${fixModels(ev).join(", ")}; a change is (with fix) − (as written).`,
      rows: neg,
    });
  }
  return groups;
}

export function fixModels(ev) {
  return [...new Set((ev.fix_efficacy || []).map((c) => c.model))].sort();
}

// What the table cannot show: the verdicts behind its rows. Numbers stay in the table.
export function findings(ev) {
  const out = [];
  const s3 = ev.step3_guard;
  if (s3?.decision === "adopted" && s3.comparisons.clean.v3_only === 0) {
    out.push("Given the tool results, the guard stops significantly more attacks at no added clean-block cost.");
  }
  const s2 = ev.step2_guard;
  if (s2?.decision?.new_rules === "adopted" && s2.comparisons.configured.decision === "fusion_better") {
    out.push("The guard stops significantly more attacks than Llama Guard 3 (configured) without more wrong blocks.");
  }
  const fix = Object.fromEntries((ev.fix_pooled || []).map((p) => [p.experiment, p]));
  if (fix.injecagent && fix.xstest) {
    out.push(
      "The prompt fix did not reliably reduce attacks and raised refusals of safe requests. It is optional.",
    );
  }
  if (ev.rubric_vs_plain && !ev.rubric_vs_plain.claim_allowed) {
    out.push(
      "The rubric judge is not more accurate than a plain one-question judge; it is kept for checkable, quoted evidence.",
    );
  }
  return out;
}

// Limitations, with names and counts from the evidence.
export function limitations(ev) {
  const out = [];
  const models = new Set([...(ev.step2_guard?.models || []), ...(ev.step3_guard?.models || []), ...fixModels(ev)]);
  if (models.size) {
    out.push(
      `Measured on small open-weight models only (${[...models].sort().join(", ")}). Results may not transfer to ` +
        "larger or frontier models.",
    );
  }
  const families = Object.values(ev.step2_guard?.by_attack_type || {}).map((t) => t.name);
  if (families.length) {
    out.push(`Guard attacks cover ${[...new Set(families)].join("; ")}. Other attack families are not yet measured.`);
  }
  if (ev.step3_guard) {
    out.push("The tool-results test reused attack wording seen during development; its cost was measured on clean transcripts only.");
  }
  const audit = (ev.judge_accuracy || []).find((j) => j.audit)?.audit;
  const missed = audit && Object.entries(audit).find(([k]) => /^oracle missed/.test(k));
  if (audit && missed) {
    out.push(
      "Oracles match exact tool names and planted secrets, so they miss tool calls written in prose. " +
        `In an LLM audit of the ${audit.disagreements} grader–oracle disagreements, ${missed[1]} were oracle misses; ` +
        "the audit is not ground truth, and the reported accuracy stays grader vs oracle.",
    );
  }
  const checks = [...new Set((ev.judge_accuracy || []).map((j) => j.check))];
  if (checks.length) {
    out.push(
      `Grader accuracy is measured for ${checks.length} checks (${checks.map((c) => c.replace(/_/g, " ")).join(", ")}); ` +
        "grades for the other checks are not yet validated against oracles.",
    );
  }
  out.push("The guard is defense in depth, not a sandbox. OWASP Agentic 2026 codes are provisional.");
  return out;
}
