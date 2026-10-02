import React from "react";
import { Helmet } from "react-helmet-async";
import evidence from "../content/evidence.json";
import { fixVerdict, graderName, interval, points as signedPoints, significanceByGrader } from "../lib/evidence";
import { DataTable, Doc, DocHeader } from "../components/doc";
import { DiscordantPairs, FixChanges, GraderVsBaselines, GuardTradeoff, StoppedBars } from "../components/trust/charts";
import { EXPERIMENT_NAMES, pShort } from "../components/trust/format";

// Every number comes from content/evidence.json, generated from committed evidence
// (python -m fusion_first.validate.trust_report) and checked by a test.

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
    .filter((j) => rows.length && rows.every((r) => /^[\d, −+(]/.test(String(r[j] ?? ""))));
  return <DataTable head={head} rows={rows} numeric={numeric} />;
}

const LG_VERDICT = {
  fusion_better: "Fusion stops significantly more real attacks, without significantly more wrong blocks.",
  other_better: "Llama Guard stops significantly more real attacks.",
  no_significant_difference: "no significant difference.",
};

const PRIOR_VERDICT = {
  fusion_better: "the current rules stop significantly more real attacks, without significantly more wrong blocks.",
  other_better: "the previous rules stop significantly more real attacks.",
  no_significant_difference: "no significant difference.",
};

// fig = the number of the section's first figure.
export function Step2Section({ s, fig = 1 }) {
  const rows = ["fusion", "fusion_prior", "llama_guard_a", "llama_guard_b", "union_fusion_b"].map((k) => s.systems[k]);
  const c = s.comparisons;
  const b = s.benign_heldout;
  // The external-recipient rule's count, read from the registered finding's own words.
  const dest = Number((s.findings || []).join(" ").match(/external-recipient rule[^.]*?blocked (\d+) of/)?.[1] ?? NaN);
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
    <Section title={`Request-bound guard on ${s.models.join(" and ")}`}>
      <p className="mb-3 text-sm text-app-muted">
        Current rules ({s.rules}), authorization required: every tool call that is not a read must be covered by the
        user's own request, and after untrusted content so must a read of private data. Fresh transcripts,
        pre-registered, scored once against the previous rules ({s.prior_rules}) and Llama Guard 3.
      </p>
      <GuardTradeoff n={fig} systems={s.systems} models={s.models} />
      <Table
        head={["System", "Real attacks stopped", "Clean transcripts wrongly blocked"]}
        rows={rows.map((r) => [
          r.label,
          `${r.stopped} of ${r.attacks}, ${interval(r.recall)}`,
          `${r.blocked} of ${r.clean}, ${interval(r.over_block)}`,
        ])}
      />
      <DiscordantPairs
        n={fig + 1}
        label="Transcripts where only one guard acted"
        leftLabel="other only"
        rightLabel="Fusion only"
        groups={[
          { title: "Attacks stopped", rows: pairs("attacks", "fusion") },
          { title: "Clean transcripts wrongly blocked", rows: pairs("clean", "cost") },
        ]}
        caption="Transcripts where only one guard acted: the pairs McNemar tests. Purple: Fusion alone stopped the attack; pink: Fusion alone wrongly blocked; grey: the other guard alone."
      />
      <p className="text-xs text-app-subtle">
        Previous rules: {PRIOR_VERDICT[c.previous_rules.decision]} (McNemar {pShort(c.previous_rules.attacks.mcnemar_p)})
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Llama Guard 3 off the shelf: {LG_VERDICT[c.off_the_shelf.decision]} (McNemar {pShort(c.off_the_shelf.attacks.mcnemar_p)})
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Llama Guard 3 configured: {LG_VERDICT[c.configured.decision]} (McNemar {pShort(c.configured.attacks.mcnemar_p)})
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Legitimate actions never used in development: {b.blocked} of {b.cases} blocked (registered limit {b.max_allowed}).
        {Number.isFinite(dest) &&
          ` The external-recipient rule, unchanged and with no allowlist, blocked ${dest} of ${b.cases} (every send to the user's own address).`}
      </p>
    </Section>
  );
}

// The McNemar counts are one sentence, not a chart: the arms disagree on a handful of transcripts.
export function Step4Section({ s }) {
  const u = s.utility_benign;
  const at = s.attack_success_in_scope;
  const c = s.comparisons.cost_none_vs_v3;
  const a = s.comparisons.attacks_none_vs_v3;
  const pts = (x) => `${(x * 100).toFixed(1)}`;
  const arms = [["No guard", "none"], ["Guard, without the tool results", "v2"], ["Guard, given the tool results", "v3"]];
  return (
    <Section title="The guard's cost in a live agent loop">
      <p className="mb-3 text-sm text-app-muted">
        AgentDojo user tasks run through real tools by {s.model}; the published guard configuration (rules {s.rules})
        checks every tool call and a blocked call does not run. Held-out tasks, pre-registered, scored once.
      </p>
      <DataTable
        head={["Arm", "Legitimate tasks completed", "In-scope attacks that succeeded"]}
        rows={arms.map(([label, k]) => [label, `${u[k].k} of ${u[k].n}, ${interval(u[k])}`, `${at[k].k} of ${at[k].n}, ${interval(at[k])}`])}
      />
      <p className="mt-3 text-xs text-app-subtle">
        Cost: {c.a_only} tasks completed only without the guard, {c.b_only} only with it ({pShort(c.p)}); completion
        fell {pts(c.drop.point)} points (95% {pts(c.drop.low)} to {pts(c.drop.high)}) against a registered margin of{" "}
        {pts(c.margin)}. Decision: {c.non_inferior ? "within the margin" : "over the margin"}. Attacks (descriptive):{" "}
        {a.a_only} succeeded only without the guard, {a.b_only} only with it ({pShort(a.p, { ns: true })}).
      </p>
    </Section>
  );
}

export function Step3Section({ s, fig = 1 }) {
  const rows = ["v3", "v2"].map((k) => s.arms[k]);
  const a = s.comparisons.attacks;
  const cl = s.comparisons.clean;
  const { v3, v2 } = s.arms;
  const arm = (r, label, tone, part) => {
    const src = part ? r[part] : r;
    return src && { label, tone, stopped: src.stopped, attacks: src.attacks };
  };
  const note = a && (
    <>
      McNemar, transcripts where the arms disagree: {a.v3_only} attacks stopped only with the tool results,{" "}
      {a.v2_only} only without ({pShort(a.p)}).{" "}
      {cl &&
        (cl.v3_only === 0 && cl.v2_only === 0
          ? "Wrong blocks on clean transcripts: identical in both arms."
          : `Clean transcripts wrongly blocked only with them: ${cl.v3_only}; only without: ${cl.v2_only} (${pShort(cl.p, { ns: true })}).`)}
    </>
  );
  return (
    <Section title="The guard given the tool results">
      <p className="mb-3 text-sm text-app-muted">
        Same rules ({s.rules}), with and without the text of the tool results the agent saw. Given it, a read that
        text asks for and the user did not is blocked when the text also asks to send data to an outside address not
        on the allowlist; no send call is needed, and a read the user asked for passes. Fresh transcripts of{" "}
        {s.models.join(" and ")}, pre-registered, scored once.
      </p>
      {v3 && v2 && (
        <StoppedBars
          n={fig}
          label="Attacks stopped with and without the tool results"
          note={note}
          rows={[
            { heading: "All attacks" },
            arm(v3, "With the tool results", "fusion"),
            arm(v2, "Without them", "grey"),
            { heading: "Data stealing" },
            arm(v3, "With the tool results", "fusion", "data_stealing"),
            arm(v2, "Without them", "grey", "data_stealing"),
          ]}
          caption="Attacks stopped by the same rules with and without the tool results. Purple: with them; grey: without (as step 2). Fill: stopped; outline: every attack."
        />
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
        Decision: {s.decision}. Attack wording was seen in development; cost measured on clean transcripts only.
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
  // Figures are numbered in page order; a section that is absent takes no number.
  let fig = 0;
  const judgeFig = judge.length ? ++fig : null;
  const step2Fig = evidence.step2_guard ? fig + 1 : null;
  if (step2Fig) fig += 2;
  const step3Fig = evidence.step3_guard ? ++fig : null;
  const fixFig = evidence.fix_efficacy ? ++fig : null;
  // The local grader's pre-registered bar: both checks at the policy floor (evals/policy.yaml).
  const lg = evidence.local_grader;
  const lgChecks = Object.values(lg?.per_check || {});
  const floor = lgChecks[0]?.floor;
  const belowFloor = (j) => lg && j.grader === lg.grader && lg.per_check?.[j.check]?.meets === false;
  const expName = (e) => EXPERIMENT_NAMES[e] || e;
  return (
    <Doc wide>
      <Helmet>
        <title>How far to trust Fusion | Fusion First</title>
      </Helmet>
      <DocHeader title="How far to trust Fusion">
        <p>
          Every table and figure is generated from committed evidence files under{" "}
          <code className="inline-code">evals/</code>. Intervals are 95%; paired comparisons use McNemar tests.
        </p>
      </DocHeader>

      <Section title="Grader accuracy vs oracle labels">
        {judge.length === 0 ? (
          <NotYet what="grader accuracy against deterministic oracles" />
        ) : (
          <>
            <GraderVsBaselines n={judgeFig} rows={judge} checkNames={CHECK_NAMES} floor={floor?.f1} />
            <Table
              head={["Check", "Grader", "n", "Accuracy", "Recall", "Specificity", "Regex baseline F1", "Grader F1"]}
              rows={judge.map((j) => [
                CHECK_NAMES[j.check] || j.check,
                belowFloor(j) ? `${graderName(j.grader)} (below the floor)` : graderName(j.grader),
                j.n,
                interval(j.accuracy),
                interval(j.recall),
                interval(j.specificity),
                j.baselines?.naive_regex ? j.baselines.naive_regex.f1.toFixed(2) : "–",
                j.f1.toFixed(2),
              ])}
            />
            {lg && floor && (
              <p className="mt-3 text-xs text-app-subtle">
                {lg.meets_floor
                  ? `${graderName(lg.grader)}: at or above the policy floor (accuracy and F1 ${floor.accuracy.toFixed(2)}) on every check.`
                  : `${graderName(lg.grader)}: below the policy floor (accuracy and F1 ${floor.accuracy.toFixed(2)}) on ${lgChecks.filter((c) => !c.meets).length} of ${lgChecks.length} checks, so it is not recommended.`}
              </p>
            )}
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
        <Section title="Rubric grading vs one plain question">
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
              ? "Rubric grading is significantly more accurate than one plain question to the grader (pre-registered rule met)."
              : "Rubric grading is no more accurate than one plain question to the grader."}
          </p>
        </Section>
      )}

      {evidence.step2_guard && <Step2Section s={evidence.step2_guard} fig={step2Fig} />}

      {evidence.step3_guard && <Step3Section s={evidence.step3_guard} fig={step3Fig} />}

      {evidence.step4_agentdojo && <Step4Section s={evidence.step4_agentdojo} />}

      <Section title="Prompt fix: effect and cost">
        {evidence.fix_pooled && (
          <div className="mb-4">
            <Table
              head={["Experiment", "Pairs", "As written", "With fix", "Change", "Verdict"]}
              rows={evidence.fix_pooled.map((p) => [
                `${expName(p.experiment)}, all models`,
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
            <FixChanges n={fixFig} cells={evidence.fix_efficacy} />
            <Table
              head={["Experiment", "Model", "Pairs", "As written", "With fix", "Verdict"]}
              rows={evidence.fix_efficacy.map((c) => [
                expName(c.experiment),
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

      <Section title="Claude Code guard hook">
        {guard.length === 0 ? (
          <NotYet what="the guard hook on held-out tool calls" />
        ) : (
          <>
            <Table
              head={["Benign calls", "Prompted", "Attacks", "Caught"]}
              rows={guard.map((g) => [
                g.benign_n,
                interval(g.over_block),
                g.attack_n,
                interval(g.recall) + (g.recall_sensitivity ? ` · ${interval(g.recall_sensitivity)} adjusted` : ""),
              ])}
            />
            <p className="mt-3 text-xs text-app-subtle">
              Held-out tool calls, scored once. Defense in depth, not a
              sandbox.
            </p>
          </>
        )}
      </Section>
    </Doc>
  );
}
