import React from "react";
import { Helmet } from "react-helmet-async";
import evidence from "../content/evidence.json";
import { fixVerdict, interval, points as signedPoints, pValue, significanceByGrader } from "../lib/evidence";
import { DataTable, Doc, DocHeader } from "../components/doc";
import { DiscordantPairs, FixChanges, GraderVsBaselines, GuardTradeoff, StoppedBars } from "../components/trust/charts";

// Every number on this page comes from frontend/src/content/evidence.json, which is GENERATED from
// committed evidence files (python -m fusion_first.validate.trust_report) and checked by a test — the
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
    <section className="doc-section">
      <h2 className="doc-h2 mb-4">{title}</h2>
      {children}
    </section>
  );
}

// Count and interval cells are set in tabular mono; text cells stay in the reading face.
function Table({ head, rows }) {
  const numeric = head
    .map((_, j) => j)
    .filter((j) => rows.length && rows.every((r) => /^[\d—−+(]/.test(String(r[j] ?? ""))));
  return <DataTable head={head} rows={rows} numeric={numeric} />;
}

// The small-model measurements: the fresh re-measurement of the rules of that time once it exists (the
// first measurement led to a rule fix); the first one stays disclosed.
export function GuardrailSection({ runtime }) {
  const first = runtime.first_measurement;
  const rules = runtime.rules ? `rules ${runtime.rules}` : "pre-registered";
  return (
    <Section title="Runtime guardrail on real attacks">
      <p className="mb-3 text-sm text-app-muted">
        {runtime.fresh
          ? `Fresh transcripts, ${rules}, ${runtime.models.length} small models. First measurement (older rules): ${first.all.stopped} of ${first.all.attacks} stopped.`
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

const PRIOR_VERDICT = {
  fusion_better: "the current rules stop significantly more real attacks, without significantly more wrong blocks.",
  other_better: "the previous rules stop significantly more real attacks.",
  no_significant_difference: "no significant difference.",
};

// The current rules' pre-registered measurement: fresh 7-8B transcripts, scored once against the
// previous rules and Llama Guard 3 on the same transcripts.
export function Step2Section({ s }) {
  const rows = ["fusion", "fusion_prior", "llama_guard_a", "llama_guard_b", "union_fusion_b"].map((k) => s.systems[k]);
  const c = s.comparisons;
  const b = s.benign_heldout;
  const pair = (label, cmp, key) => cmp?.[key] && { label, left: cmp[key].other_only, right: cmp[key].fusion_only, p: cmp[key].mcnemar_p };
  const pairs = (key, tone) =>
    [
      pair("Previous rules", c.previous_rules, key),
      pair("Llama Guard 3, off the shelf", c.off_the_shelf, key),
      pair("Llama Guard 3, configured", c.configured, key),
    ]
      .filter(Boolean)
      .map((r) => ({ ...r, tone }));
  return (
    <Section title={`Request-bound guardrail on ${s.models.join(" and ")}`}>
      <p className="mb-3 text-sm text-app-muted">
        Current rules ({s.rules}): after untrusted content, a tool call must be covered by the user's own request.
        Fresh transcripts, pre-registered, scored once against the previous rules ({s.prior_rules}) and Llama Guard 3.
      </p>
      <GuardTradeoff systems={s.systems} models={s.models} />
      <div className="chart-grid">
        <StoppedBars
          label="Attacks stopped by the current rules, by attack type"
          rows={[
            ...Object.values(s.by_attack_type || {}).map((t) => ({ label: t.name, stopped: t.stopped, attacks: t.attacks })),
            s.systems.fusion && { label: "All", stopped: s.systems.fusion.stopped, attacks: s.systems.fusion.attacks },
          ].filter(Boolean)}
          caption="Current rules. Purple fill: stopped; outline: every attack of that type."
        />
        <DiscordantPairs
          label="Transcripts where only one guard acted"
          leftLabel="other only"
          rightLabel="Fusion only"
          groups={[
            { title: "Attacks stopped", rows: pairs("attacks", "fusion") },
            { title: "Clean wrongly blocked", rows: pairs("clean", "cost") },
          ]}
          caption="Transcripts where only one guard acted, the pairs McNemar tests. Purple: Fusion stopped an attack the other missed; pink: Fusion alone wrongly blocked; grey: the other guard alone."
        />
      </div>
      <Table
        head={["System", "Real attacks stopped", "Clean transcripts wrongly blocked"]}
        rows={rows.map((r) => [
          r.label,
          `${r.stopped} of ${r.attacks}, ${interval(r.recall)}`,
          `${r.blocked} of ${r.clean}, ${interval(r.over_block)}`,
        ])}
      />
      <p className="mt-3 text-xs text-app-subtle">
        Previous rules: {PRIOR_VERDICT[c.previous_rules.decision]} (McNemar {pValue(c.previous_rules.attacks.mcnemar_p)})
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Llama Guard 3 off the shelf: {LG_VERDICT[c.off_the_shelf.decision]} (McNemar {pValue(c.off_the_shelf.attacks.mcnemar_p)})
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Llama Guard 3 configured: {LG_VERDICT[c.configured.decision]} (McNemar {pValue(c.configured.attacks.mcnemar_p)})
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Legitimate actions never used in development: {b.blocked} of {b.cases} blocked (registered limit {b.max_allowed}).
      </p>
    </Section>
  );
}

export function Step3Section({ s }) {
  const rows = ["v3", "v2"].map((k) => s.arms[k]);
  const a = s.comparisons.attacks;
  const cl = s.comparisons.clean;
  const arm = (r, tone, part) => (part ? r[part] && { label: r.label, tone, ...r[part] } : { label: r.label, tone, stopped: r.stopped, attacks: r.attacks });
  const [v3, v2] = [s.arms.v3, s.arms.v2];
  return (
    <Section title="The guard given the tool results">
      <p className="mb-3 text-sm text-app-muted">
        Same rules ({s.rules}), with and without the tool results the agent saw: a read they ask for, alongside a send
        to an outside address, is blocked. Fresh transcripts of {s.models.join(" and ")}, pre-registered, scored once.
      </p>
      {v3 && v2 && (
        <div className="chart-grid">
          <StoppedBars
            label="Attacks stopped with and without the tool results"
            rows={[
              { heading: "All attacks" },
              arm(v3, "fusion"),
              arm(v2, "grey"),
              { heading: "Data stealing" },
              arm(v3, "fusion", "data_stealing"),
              arm(v2, "grey", "data_stealing"),
            ].filter(Boolean)}
            caption="Purple: given the tool results. Grey: without them. Fill: stopped; outline: every attack."
          />
          <DiscordantPairs
            label="Transcripts where only one arm acted"
            leftLabel="without only"
            rightLabel="with only"
            groups={[
              { title: "Attacks stopped", rows: a ? [{ label: "With vs without the tool results", left: a.v2_only, right: a.v3_only, p: a.p, tone: "fusion" }] : [] },
              { title: "Clean wrongly blocked", rows: cl ? [{ label: "With vs without the tool results", left: cl.v2_only, right: cl.v3_only, p: cl.p, tone: "cost" }] : [] },
            ]}
            caption="Transcripts where only one arm acted, the pairs McNemar tests. Purple: stopped only with the tool results; pink: wrongly blocked only with them; grey: only without."
          />
        </div>
      )}
      <Table
        head={["Guard", "Real attacks stopped", "Data-stealing stopped", "Clean transcripts wrongly blocked"]}
        rows={rows.map((r) => [
          r.label,
          `${r.stopped} of ${r.attacks}, ${interval(r.recall)}`,
          `${r.data_stealing.stopped} of ${r.data_stealing.attacks}, ${interval(r.data_stealing.recall)}`,
          `${r.blocked} of ${r.clean}, ${interval(r.over_block)}`,
        ])}
      />
      <p className="mt-3 text-xs text-app-subtle">
        Stopped only with the tool results: {a.v3_only}; only without: {a.v2_only} (McNemar {pValue(a.p)}). Decision: {s.decision}.
        Attack wording was seen in development; cost measured on clean transcripts only.
      </p>
    </Section>
  );
}

function NotYet({ what }) {
  return (
    <p className="border-l-2 border-app-border-strong pl-3 text-sm text-app-muted">
      Not yet measured: {what}.
    </p>
  );
}

export default function Trust() {
  const judge = evidence.judge_accuracy || [];
  const guard = evidence.guard_heldout || [];
  return (
    <Doc wide>
      <Helmet>
        <title>How far to trust Fusion | Fusion First</title>
      </Helmet>
      <DocHeader eyebrow="Evidence" title="How far to trust Fusion">
        <p>
          Every table is generated from committed evidence files under <code className="inline-code">evals/</code>.
          Intervals are 95%; paired comparisons use McNemar tests.
        </p>
      </DocHeader>

      <Section title="Judge accuracy vs oracle labels">
        {judge.length === 0 ? (
          <NotYet what="grader accuracy against deterministic oracles" />
        ) : (
          <>
            <GraderVsBaselines rows={judge} checkNames={CHECK_NAMES} />
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

      {evidence.step2_guard && <Step2Section s={evidence.step2_guard} />}

      {evidence.step3_guard && <Step3Section s={evidence.step3_guard} />}

      {evidence.runtime_guardrail && <GuardrailSection runtime={evidence.runtime_guardrail} />}

      {evidence.guard_vs_llama_guard && <LlamaGuardSection cmp={evidence.guard_vs_llama_guard} />}

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
          <>
          <FixChanges cells={evidence.fix_efficacy} />
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
          </>
        ) : (
          <NotYet what="the as-written vs fixed prompt comparison on local models" />
        )}
      </Section>

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
    </Doc>
  );
}
