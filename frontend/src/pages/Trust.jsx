import React from "react";
import { Helmet } from "react-helmet-async";
import evidence from "../content/evidence.json";
import { fixVerdict, interval, points as signedPoints, significanceByGrader } from "../lib/evidence";
import { DataTable, Doc, DocHeader } from "../components/doc";
import { DiscordantPairs, FixChanges, GraderVsBaselines, GuardTradeoff, StoppedBars } from "../components/trust/charts";
import { EXPERIMENT_NAMES, pShort } from "../components/trust/format";

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
// first measurement led to a rule fix); the first one stays disclosed. supersededBy = the rules measured
// since (step 2), when they differ: these numbers then describe the previous rules, not the current guard.
export function GuardrailSection({ runtime, supersededBy }) {
  const first = runtime.first_measurement;
  const rules = runtime.rules ? `rules ${runtime.rules}` : "pre-registered";
  const old = supersededBy && runtime.rules && supersededBy !== runtime.rules;
  return (
    <Section title={old ? "Runtime guard on real attacks: previous rules" : "Runtime guard on real attacks"}>
      <p className="mb-3 text-sm text-app-muted">
        {runtime.fresh
          ? `Fresh transcripts, ${rules}, ${runtime.models.length} small models. First measurement (older rules): ${first.all.stopped} of ${first.all.attacks} stopped.`
          : `${runtime.models.length} models, pre-registered.`}
        {old && ` Superseded by the current rules (${supersededBy}) above; these numbers do not describe them.`}
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
  const line = (name, c) => `${name}: ${LG_VERDICT[c.decision]} (McNemar ${pShort(c.attacks.mcnemar_p)})`;
  return (
    <Section title={`Runtime guard vs Llama Guard 3 (${cmp.model})`}>
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
// previous rules and Llama Guard 3 on the same transcripts. fig = the number of its first figure.
export function Step2Section({ s, fig = 1 }) {
  const rows = ["fusion", "fusion_prior", "llama_guard_a", "llama_guard_b", "union_fusion_b"].map((k) => s.systems[k]);
  const c = s.comparisons;
  const b = s.benign_heldout;
  // The external-recipient rule's count on the same held-out actions: a field once the generator emits it,
  // else the registered finding's own words.
  const dest =
    b.blocked_by_destination_rule ??
    Number((s.findings || []).join(" ").match(/external-recipient rule[^.]*?blocked (\d+) of/)?.[1] ?? NaN);
  const pair =(label, cmp, key) => cmp?.[key] && { label, left: cmp[key].other_only, right: cmp[key].fusion_only, p: cmp[key].mcnemar_p };
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
        caption="Transcripts where only one guard acted: the pairs McNemar tests (n.s.: p≥0.05). Purple: Fusion alone stopped the attack; pink: Fusion alone wrongly blocked; grey: the other guard alone."
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
      <StoppedBars
        n={fig + 2}
        label="Attacks stopped by the current rules, by attack type"
        rows={[
          ...Object.values(s.by_attack_type || {}).map((t) => ({ label: t.name.charAt(0).toUpperCase() + t.name.slice(1), stopped: t.stopped, attacks: t.attacks })),
          s.systems.fusion && { label: "All", stopped: s.systems.fusion.stopped, attacks: s.systems.fusion.attacks },
        ].filter(Boolean)}
        caption="Attacks stopped by the current rules, by attack type. Purple fill: stopped; outline: every attack of that type."
      />
      <p className="text-xs text-app-subtle">
        Legitimate actions never used in development: {b.blocked} of {b.cases} blocked (registered limit {b.max_allowed}).
        {Number.isFinite(dest) &&
          ` The external-recipient rule, unchanged and with no allowlist, blocked ${dest} of ${b.cases} (every send to the user's own address).`}
      </p>
    </Section>
  );
}

// Same rules with and without the tool results. The McNemar counts are one sentence, not a chart: the
// arms disagree on a handful of transcripts, all in one direction.
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
  if (step2Fig) fig += 3;
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
                belowFloor(j) ? `${j.grader}, below the policy floor` : j.grader,
                j.n,
                interval(j.accuracy),
                interval(j.recall),
                interval(j.specificity),
                j.baselines?.naive_regex ? j.baselines.naive_regex.f1.toFixed(2) : "—",
                j.f1.toFixed(2),
              ])}
            />
            {lg && floor && (
              <p className="mt-3 text-xs text-app-subtle">
                {lg.meets_floor
                  ? `${lg.grader}: meets the policy floor (accuracy ${floor.accuracy.toFixed(2)}, F1 ${floor.f1.toFixed(2)}) on every check; the pre-registered bar is met.`
                  : `${lg.grader}: below the policy floor (accuracy ${floor.accuracy.toFixed(2)}, F1 ${floor.f1.toFixed(2)}) on ${lgChecks.filter((c) => !c.meets).length} of ${lgChecks.length} checks; the pre-registered bar for staying the default free grader (both checks at the floor) is not met.`}
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

      {evidence.runtime_guardrail && (
        <GuardrailSection runtime={evidence.runtime_guardrail} supersededBy={evidence.step2_guard?.rules} />
      )}

      {evidence.guard_vs_llama_guard && <LlamaGuardSection cmp={evidence.guard_vs_llama_guard} />}

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

      {evidence.value_ledger && (
        <Section title="Value ledger: fix vs guard">
          <p className="mb-3 text-sm text-app-muted">First-run transcripts.</p>
          <Table
            head={["Model", "Attacks", "Removed by fix", "Caused by fix", "Stopped by guard", "Either", "Neither"]}
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
