import React from "react";
import evidence from "../content/evidence.json";
import { fixVerdict, interval, significanceByGrader } from "../lib/evidence";

// Every number on this page comes from frontend/src/content/evidence.json, which is GENERATED from
// committed evidence files (python -m fusion.validate.trust_report) and checked by a test — the
// page can't show a number the evidence doesn't back.

const CHECK_NAMES = {
  direct_prompt_injection: "Prompt injection",
  system_prompt_leakage: "System-prompt / secret leakage",
  excessive_agency: "Excessive agency",
  data_exfiltration: "Data exfiltration",
  instruction_following: "Instruction following",
};

function Section({ title, children }) {
  return (
    <section className="mb-12">
      <h2 className="mb-3 text-xl font-semibold text-app-text">{title}</h2>
      {children}
    </section>
  );
}

function Table({ head, rows }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-app-border">
      <table className="w-full text-left text-sm">
        <thead className="bg-surface-2 text-app-muted">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-app-border text-app-text">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2 align-top">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// The headline is the fresh re-measurement of the current rules once it exists (the first measurement
// led to a rule fix, so it no longer describes the rules as shipped); the first one stays disclosed.
export function GuardrailSection({ runtime }) {
  const first = runtime.first_measurement;
  return (
    <Section title="Runtime guardrail on real attacks">
      <p className="mb-3 text-sm text-app-muted">
        {runtime.fresh
          ? `Fresh transcripts, current rules, ${runtime.models.length} models. First measurement (older rules): ${first.all.stopped} of ${first.all.attacks} stopped.`
          : `${runtime.models.length} models, pre-registered.`}
      </p>
      <Table
        head={["Attack", "Attacks", "Stopped", "Clean", "Wrongly blocked"]}
        rows={[
          ...Object.values(runtime.by_attack_type).map((s) => [
            s.name,
            s.attacks,
            interval(s.recall),
            s.clean,
            interval(s.over_block),
          ]),
          ["All", runtime.all.attacks, interval(runtime.all.recall), runtime.all.clean, interval(runtime.all.over_block)],
        ]}
      />
    </Section>
  );
}

const LG_VERDICT = {
  fusion_better: "Fusion stops significantly more real attacks, without significantly more wrong blocks.",
  other_better: "Llama Guard stops significantly more real attacks.",
  no_significant_difference: "no significant difference.",
};

export function LlamaGuardSection({ cmp }) {
  const rows = ["fusion", "llama_guard_a", "llama_guard_b", "union_fusion_b"].map((k) => cmp.systems[k]);
  const line = (name, c) =>
    `${name}: ${LG_VERDICT[c.decision]} (McNemar p=${c.attacks.mcnemar_p.toFixed(4)})`;
  return (
    <Section title={`Runtime guardrail vs Llama Guard 3 (${cmp.model})`}>
      <Table
        head={["System", "Real attacks stopped", "Clean transcripts wrongly blocked"]}
        rows={rows.map((s) => [
          s.label,
          `${s.stopped} of ${s.attacks}, ${interval(s.recall)}`,
          `${s.blocked} of ${s.clean}, ${interval(s.over_block)}`,
        ])}
      />
      <p className="mt-3 text-xs text-app-subtle">{line("Off the shelf", cmp.comparisons.off_the_shelf)}</p>
      <p className="mt-1 text-xs text-app-subtle">{line("Configured", cmp.comparisons.configured)}</p>
    </Section>
  );
}

function NotYet({ what }) {
  return (
    <p className="rounded-lg border border-dashed border-app-border p-4 text-sm text-app-muted">
      Not yet measured: {what}.
    </p>
  );
}

// A signed difference in percentage points with its 95% range, e.g. "−1 pt (−6 to +4)".
function signedPoints(d) {
  if (!d) return "—";
  const f = (x) => {
    const v = Math.round(x * 100);
    return v > 0 ? `+${v}` : `${v}`.replace("-", "−");
  };
  return `${f(d.point)} pts (${f(d.low)} to ${f(d.high)})`;
}

export default function Trust() {
  const judge = evidence.judge_accuracy || [];
  const guard = evidence.guard_heldout || [];
  return (
    <main style={{ maxWidth: "1000px", margin: "0 auto", padding: "clamp(2rem, 6vw, 3.5rem) 1rem" }}>
      <h1 style={{ fontSize: "clamp(1.8rem, 5vw, 2.6rem)", margin: "0 0 0.75rem", color: "var(--text)" }}>
        How far to trust Fusion
      </h1>
      <div className="mb-10" />

      <Section title="Judge accuracy vs oracle labels">
        {judge.length === 0 ? (
          <NotYet what="grader accuracy against deterministic oracles" />
        ) : (
          <>
            <Table
              head={["Check", "Grader", "n", "Accuracy", "Recall", "Specificity", "Regex baseline F1", "Grader F1"]}
              rows={judge.map((j) => [
                CHECK_NAMES[j.check] || j.check,
                j.grader,
                j.n,
                interval(j.accuracy),
                interval(j.recall),
                interval(j.specificity),
                j.baselines?.naive_regex ? j.baselines.naive_regex.f1.toFixed(2) : "—",
                j.f1.toFixed(2),
              ])}
            />
            <p className="mt-3 text-xs text-app-subtle">Grader vs baselines (paired McNemar, p &lt; 0.05):</p>
            {significanceByGrader(judge).map((s) => (
              <p key={s} className="mt-1 text-xs text-app-subtle">
                {s}
              </p>
            ))}
          </>
        )}
      </Section>

      {evidence.rubric_vs_plain && (
        <Section title="Rubric judge vs a plain question">
          <Table
            head={["Check", "n", "Rubric", "Plain question", "Rubric − plain"]}
            rows={[
              ...Object.entries(evidence.rubric_vs_plain.by_check).map(([check, b]) => [
                CHECK_NAMES[check] || check,
                b.n,
                interval(b.rubric),
                interval(b.plain),
                signedPoints(b.difference),
              ]),
              [
                "Both checks",
                evidence.rubric_vs_plain.pooled.n,
                interval(evidence.rubric_vs_plain.pooled.rubric),
                interval(evidence.rubric_vs_plain.pooled.plain),
                signedPoints(evidence.rubric_vs_plain.pooled.difference),
              ],
            ]}
          />
          <p className="mt-3 text-xs text-app-subtle">
            {evidence.rubric_vs_plain.claim_allowed
              ? "The rubric is significantly more accurate than a plain question (pre-registered rule met)."
              : "The rubric is not more accurate than a plain question, and Fusion does not claim it is."}
          </p>
        </Section>
      )}

      <Section title="Prompt fix: effect and cost">
        {evidence.fix_pooled && (
          <div className="mb-4">
            <Table
              head={["Experiment", "Pairs", "As written", "With fix", "Change", "Verdict"]}
              rows={evidence.fix_pooled.map((p) => [
                `${p.experiment} (all models)`,
                p.n_pairs,
                interval(p.baseline_rate),
                interval(p.hardened_rate),
                signedPoints(p.change),
                p.verdict,
              ])}
            />
          </div>
        )}
        {evidence.fix_efficacy ? (
          <Table
            head={["Experiment", "Model", "Pairs", "As written", "With fix", "Verdict"]}
            rows={evidence.fix_efficacy.map((c) => [
              c.experiment,
              c.model,
              c.n_paired,
              interval(c.baseline_rate),
              interval(c.hardened_rate),
              fixVerdict(c).text,
            ])}
          />
        ) : (
          <NotYet what="the as-written vs fixed prompt comparison on local models" />
        )}
      </Section>

      {evidence.runtime_guardrail && <GuardrailSection runtime={evidence.runtime_guardrail} />}

      {evidence.guard_vs_llama_guard && <LlamaGuardSection cmp={evidence.guard_vs_llama_guard} />}

      {evidence.value_ledger && (
        <Section title="Value ledger: fix vs guardrail">
          <p className="mb-3 text-sm text-app-muted">First-run transcripts.</p>
          <Table
            head={["Model", "Attacks", "Removed by fix", "Caused by fix", "Stopped by guardrail", "Either", "Neither"]}
            rows={[
              ...Object.entries(evidence.value_ledger.by_model).map(([m, s]) => [
                m, s.found, s.fix_removed, s.fix_caused, s.guard_stopped, s.either, s.neither,
              ]),
              (() => {
                const t = evidence.value_ledger.total;
                return ["All models", t.found, t.fix_removed, t.fix_caused, t.guard_stopped, t.either, t.neither];
              })(),
            ]}
          />
          <p className="mt-3 text-xs text-app-subtle">
            {evidence.value_ledger.fix_refusal_cost &&
              `The fix also caused ${evidence.value_ledger.fix_refusal_cost.safe_requests_newly_refused} new refusals of safe requests. `}
          </p>
        </Section>
      )}

      <Section title="Claude Code guard hook">
        {guard.length === 0 ? (
          <NotYet what="the guard hook on held-out tool calls" />
        ) : (
          <>
            <Table
              head={["Set", "Benign calls", "Prompted", "Attacks", "Caught", "Status"]}
              rows={guard.map((g) => [
                g.set,
                g.benign_n,
                interval(g.over_block),
                g.attack_n,
                interval(g.recall) + (g.recall_sensitivity ? ` · ${interval(g.recall_sensitivity)} adjusted` : ""),
                g.status,
              ])}
            />
            <p className="mt-3 text-xs text-app-subtle">
              Defense in depth, not a sandbox.
            </p>
          </>
        )}
      </Section>
    </main>
  );
}
