// The overview page's results table and findings, built from the generated evidence
// (frontend/src/content/evidence.json). Nothing here carries a number of its own: a block the evidence
// lacks is left out, and a result that was not adopted is not presented as one.
import { graderName, pValue } from "./evidence";

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
      note: `Pre-registered; fresh transcripts of ${s3.models.join(" and ")}; rules ${s3.rules}; adopted.`,
      rows: [
        { label: "Tool hijacks stopped (InjecAgent)", n: v3.attacks, est: v3.recall, scale: "rate", tone: "good", detail: count(v3.stopped, v3.attacks) },
        { label: "Clean transcripts wrongly blocked", n: v3.clean, est: v3.over_block, scale: "rate", tone: "cost", detail: count(v3.blocked, v3.clean) },
        {
          label: "Tool hijacks stopped without the tool results",
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
      note: `Pre-registered; fresh transcripts of ${s2.models.join(" and ")}, the same for both; rules ${s2.rules}.`,
      rows: [
        { label: "Fusion guard: attacks stopped", n: f.attacks, est: f.recall, scale: "rate", tone: "good", detail: count(f.stopped, f.attacks) },
        { label: "Fusion guard: clean transcripts wrongly blocked", n: f.clean, est: f.over_block, scale: "rate", tone: "cost", detail: count(f.blocked, f.clean) },
        {
          label: "Llama Guard 3, configured: attacks stopped",
          n: lg.attacks,
          est: lg.recall,
          scale: "rate",
          tone: "neutral",
          detail: `${count(lg.stopped, lg.attacks)}; McNemar ${pValue(s2.comparisons.configured.attacks.mcnemar_p)}`,
        },
        { label: "Llama Guard 3, configured: clean transcripts wrongly blocked", n: lg.clean, est: lg.over_block, scale: "rate", tone: "neutral", detail: count(lg.blocked, lg.clean) },
      ],
    });
  }

  const s4 = ev.step4_agentdojo;
  if (s4) {
    const { none, v3 } = s4.utility_benign;
    const c = s4.comparisons.cost_none_vs_v3;
    groups.push({
      id: "step4",
      title: "Guard cost in a live agent loop (AgentDojo)",
      note: `Pre-registered; held-out tasks, ${s4.model}; rules ${s4.rules}; ` +
        `${c.non_inferior ? "within" : "over"} the registered margin.`,
      rows: [
        { label: "Legitimate tasks completed, no guard", n: none.n, est: none, scale: "rate", tone: "neutral", detail: count(none.k, none.n) },
        {
          label: "Legitimate tasks completed, with the guard",
          n: v3.n,
          est: v3,
          scale: "rate",
          tone: "cost",
          detail: `${count(v3.k, v3.n)}; ${c.a_only} broken, ${c.b_only} fixed; McNemar ${pValue(c.p)}`,
        },
      ],
    });
  }

  const judges = (ev.judge_accuracy || []).filter((j) => CHECK_LABELS[j.check]);
  if (judges.length) {
    const floor = ev.local_grader;
    groups.push({
      id: "judge",
      title: "Grader accuracy against deterministic oracles",
      note: "Real llama3.2:1b transcripts (InjecAgent, Gandalf); oracle labels fixed before grading; not pre-registered.",
      rows: judges.map((j) => {
        const below = floor && j.grader === floor.grader && !floor.meets_floor;
        return {
          label: `${graderName(j.grader)}, ${CHECK_LABELS[j.check]}`,
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
      label: "Rubric grading minus one plain question, accuracy",
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
      note: `Rubric: pre-registered, on the grader-accuracy items. Prompt fix: not pre-registered, pooled over ${fixModels(ev).join(", ")}. Change = with fix − as written.`,
      rows: neg,
    });
  }
  return groups;
}

function fixModels(ev) {
  return [...new Set((ev.fix_efficacy || []).map((c) => c.model))].sort();
}

// The overview's headline figures: the guard's pre-registered results, read from the evidence (never typed in).
export function headlineStats(ev) {
  const s2 = ev.step2_guard;
  if (s2?.decision?.new_rules !== "adopted") return [];
  const f = s2.systems.fusion;
  const lg = s2.systems.llama_guard_b;
  const pc = (x) => `${Math.round(x * 100)}%`;
  const out = [
    { value: pc(f.recall.point), label: "of real attacks stopped by the guard", note: count(f.stopped, f.attacks) },
    { value: pc(lg.recall.point), label: "stopped by Llama Guard 3 on the same attacks", note: count(lg.stopped, lg.attacks), muted: true },
    { value: pc(f.over_block.point), label: "of clean transcripts wrongly blocked", note: count(f.blocked, f.clean) },
  ];
  const s3 = ev.step3_guard;
  if (s3?.decision === "adopted") {
    const ds = s3.arms.v3.data_stealing;
    out.push({ value: pc(ds.recall.point), label: "of data-stealing hijacks stopped, given the tool results", note: count(ds.stopped, ds.attacks) });
  }
  return out;
}

// What the table cannot show: the verdicts behind its rows. Numbers stay in the table.
export function findings(ev) {
  const out = [];
  const s3 = ev.step3_guard;
  if (s3?.decision === "adopted" && s3.comparisons.clean.v3_only === 0) {
    out.push("Given the tool results, the guard stops significantly more tool hijacks and wrongly blocks no more clean transcripts.");
  }
  const s2 = ev.step2_guard;
  const lg = s2?.comparisons?.configured;
  if (s2?.decision?.new_rules === "adopted" && lg?.decision === "fusion_better") {
    const fewer = lg.clean && lg.clean.mcnemar_p < 0.05 && lg.clean.other_only > lg.clean.fusion_only;
    out.push(
      "The guard stops significantly more attacks than Llama Guard 3 (configured) and wrongly blocks " +
        (fewer ? "significantly fewer clean transcripts." : "no more clean transcripts."),
    );
  }
  const s4 = ev.step4_agentdojo;
  if (s4) {
    const c = s4.comparisons.cost_none_vs_v3;
    out.push(
      c.non_inferior
        ? "In a live agent loop, the guard's cost on legitimate tasks stayed within its registered margin."
        : `In a live agent loop, the guard broke ${c.a_only} legitimate tasks the agent otherwise completed, over its ` +
          "registered margin: mostly requests worded differently from the tool they need.",
    );
  }
  const fix = Object.fromEntries((ev.fix_pooled || []).map((p) => [p.experiment, p]));
  if (fix.injecagent && !/better/.test(fix.injecagent.verdict) && /worse/.test(fix.xstest?.verdict || "")) {
    out.push(
      "The prompt fix did not reliably reduce attacks and raised refusals of safe requests. It is optional.",
    );
  }
  if (ev.rubric_vs_plain && !ev.rubric_vs_plain.claim_allowed) {
    out.push(
      "Rubric grading is not more accurate than one plain question to the grader; the rubric is kept because its answers quote checkable evidence.",
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
    out.push(`The guard was tested on ${[...new Set(families)].join("; ")} only; other attack families are unmeasured.`);
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
