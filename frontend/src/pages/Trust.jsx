import React from "react";
import { Helmet } from "react-helmet-async";
import evidence from "../content/evidence.json";
import { fixVerdict, graderName, interval, pct, points as signedPoints, significanceByGrader } from "../lib/evidence";
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

// A registered rule change that did not clear its bar: both rule sets on the same sealed calls.
export function Step5Section({ s }) {
  const pts = (x) => `${(x * 100).toFixed(1)}`;
  const rows = [
    ["Legitimate (a block is wrong)", s.legitimate],
    ["Hijacked (a block is right)", s.hijack],
    ["Hijacked, no address in the call", s.hijack_binding_only],
  ];
  const d = s.hijack.difference;
  return (
    <Section title="Request binding by verb class">
      <p className="mb-3 text-sm text-app-muted">
        Candidate rules ({s.rules.new}) that bind a request to a tool by verb class, against the published rules
        ({s.rules.old}), on the same sealed calls written blind by {s.authors} Claude Sonnet authors over new tool
        catalogues. No model runs in the scored pass. Pre-registered, scored once.
      </p>
      <DataTable
        head={["Sealed calls", "Published rules blocked", "Candidate rules blocked"]}
        rows={rows.map(([label, b]) => [label, `${b.old.k} of ${b.old.n}, ${interval(b.old)}`, `${b.new.k} of ${b.new.n}, ${interval(b.new)}`])}
      />
      <p className="mt-3 text-xs text-app-subtle">
        Cost: {s.legitimate.old_only} legitimate calls blocked by the published rules only, {s.legitimate.new_only} by
        the candidate only ({pShort(s.legitimate.mcnemar_p)}); the candidate's wrongly-blocked upper bound is{" "}
        {pts(s.legitimate.new.high)}% against a registered ceiling of {pts(s.ceiling)}%. Protection: the blocked share
        of hijacked calls moved {pts(d.point)} points (95% {pts(d.low)} to {pts(d.high)}) against a margin of -
        {pts(s.margin)}. Decision: {s.verdict}{s.decision.adopt ? "." : "; the published rules stay the default."}{" "}
        Authored calls, not a model's own trajectories.
      </p>
    </Section>
  );
}

const countOf = (r) => `${r.k} of ${r.n}, ${interval(r)}`;

// The guard against classifiers built to detect prompt injection. The verdict sentences come from the registered
// rule (trust_report.py), so the copy follows the result whichever way it falls.
export function DetectorsStudySection({ s }) {
  const sets = Object.entries(s.sets);
  return (
    <Section title="Guard vs dedicated injection detectors">
      <p className="mb-3 text-sm text-app-muted">
        Fresh InjecAgent transcripts of {s.models.join(" and ")}: {s.n_items} items, each run with the injection as
        written, behind an "ignore all previous instructions" prefix, and with a benign filler in its place. The guard
        ({s.rules}) and Llama Guard 3 read the model's reply; the classifiers read the tool result. Pre-registered,
        scored once.
      </p>
      <DataTable
        head={["System", ...sets.map(([, v]) => `Attacks stopped, ${v.label}`), "Benign runs wrongly blocked"]}
        rows={s.systems.map(({ key, label }) => [
          label,
          ...sets.map(([, v]) => countOf(v.attacks.systems[key])),
          countOf(s.control.systems[key]),
        ])}
      />
      {sets.map(([name, v], i) => (
        <p key={name} className={`${i ? "mt-1" : "mt-3"} text-xs text-app-subtle`}>
          Attacks, {v.label}: {s.baselines.map((b) => s.verdict_text[name][b]).join("; ")}.
        </p>
      ))}
      <p className="mt-1 text-xs text-app-subtle">
        Benign runs: {s.baselines.map((b) => s.verdict_text.control[b]).join("; ")}.
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        One benchmark family in a single-turn harness; the classifiers run at their default threshold.
      </p>
    </Section>
  );
}

// Llama Guard 3 on the job it was built for, beside a guard that has no rules for it.
export function ContentSafetySection({ s }) {
  const c = s.comparisons.unsafe;
  return (
    <Section title="Content safety: Llama Guard 3 on its own job">
      <p className="mb-3 text-sm text-app-muted">
        Llama Guard 3 is a content-safety classifier. Both systems on {s.unsafe.n + s.safe.n} prompts with published
        labels ({Object.values(s.sources).join(", ")}): Llama Guard 3 off the shelf, and the guard ({s.rules}) flagged
        when either of its text entry points does not allow. Pre-registered, scored once.
      </p>
      <DataTable
        head={["System", "Unsafe prompts flagged", "Safe prompts wrongly flagged"]}
        rows={s.systems.map(({ key, label }) => [label, countOf(s.unsafe.systems[key]), countOf(s.safe.systems[key])])}
      />
      <p className="mt-3 text-xs text-app-subtle">
        Verdict: {s.verdict_text} ({c.reference_only} flagged only by Llama Guard 3, {c.other_only} only by the guard;{" "}
        {pShort(c.mcnemar_p)}). The guard has no content-safety rules: it gates tool calls and redacts secrets.
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

// Per-decision latency as a reader scans it: <0.01 ms, 0.04 ms, 14 ms, 2.4 s.
function ms(x) {
  if (x === null || x === undefined) return "–";
  if (x >= 1000) return `${(x / 1000).toFixed(1)} s`;
  if (x >= 10) return `${Math.round(x)} ms`;
  if (x >= 1) return `${x.toFixed(1)} ms`;
  return x < 0.01 ? "<0.01 ms" : `${x.toFixed(2)} ms`;
}

const flagged = (k, n, iv) => (n ? `${k} of ${n}, ${interval(iv)}` : "–");

// A primary outcome to one decimal, so a value just under its bar never reads as meeting it.
const pct1 = (x) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(1)}%`);
const interval1 = (iv) => `${pct1(iv.point)} (${pct1(iv.low)}–${pct1(iv.high)})`;

const SOURCE_NAMES = { injecagent: "InjecAgent", bipia: "BIPIA", deepset: "deepset", blind: "blind" };

// Latency of the registered secondaries: ms to one decimal; Ollama arms are wall time per reply, in seconds.
const lat1 = (x, sec) => {
  if (!Number.isFinite(x)) return "–";
  return sec ? `${(x / 1000).toFixed(1)} s` : `${x.toFixed(1)} ms`;
};

// A per-technique cell: positives flagged, or categories with any flag (a counted family such as BIPIA's).
function techniqueCell(c) {
  if (!c) return "–";
  if (c.categories !== undefined) return `${c.flagged} of ${c.categories}`;
  return c.n_pos ? `${c.tp} of ${c.n_pos} (${((c.tp / c.n_pos) * 100).toFixed(1)}%)` : "–";
}

// Registered secondaries of Q5 (reported, no decision). The markdown under the same heading in TRUST_REPORT.md is the model.
function SecondariesBlock({ s }) {
  const sources = s.mcnemar?.[0]?.per_source?.map((x) => x.source) || [];
  const tech = s.per_technique || {};
  const columns = tech.columns ?? [];
  const latency = s.latency || [];
  const timed = new Set(latency.map((l) => l.arm));
  const untimed = (s.mcnemar || []).filter((m) => !timed.has(m.arm));
  return (
    <>
      <p className="mt-6 mb-3 text-sm text-app-muted">
        Registered secondaries (reported, no decision; McNemar against the phrase list is not the bar).
      </p>
      <DataTable
        numeric={[1, 2, 3, 4]}
        head={["Arm", "Rows paired", "Arm right, list wrong", "List right, arm wrong", "Exact p", ...sources.map((x) => SOURCE_NAMES[x] || x)]}
        rows={(s.mcnemar || []).map((m) => [
          m.arm_label,
          m.n,
          m.arm_right_list_wrong,
          m.list_right_arm_wrong,
          pShort(m.p),
          ...sources.map((src) => {
            const c = m.per_source?.find((x) => x.source === src);
            return c
              ? `${c.arm_right_list_wrong} vs ${c.list_right_arm_wrong} (${pShort(c.p)})${c.in_source ? ", in-source" : ""}`
              : "–";
          }),
        ])}
      />
      <p className="mt-3 mb-2 text-xs text-app-subtle">
        Recall by technique at each arm's operating point; a family of categories such as BIPIA's is counted, not itemised.
      </p>
      <DataTable
        numeric={columns.map((_, i) => i + 1)}
        head={["Arm", ...columns.map((c) => c.label)]}
        rows={(tech.rows || []).map((r) => [r.arm_label, ...columns.map((c) => techniqueCell(r.cells?.[c.key]))])}
      />
      {latency.length > 0 && (
        <p className="mt-3 text-xs text-app-subtle">
          CPU latency per decision, p50 / p95:{" "}
          {latency
            .map((l) => `${l.arm_label} ${lat1(l.p50_ms, l.ollama)} / ${lat1(l.p95_ms, l.ollama)}${l.ollama ? " (Ollama wall time per reply)" : ""}`)
            .join("; ")}
          .{untimed.length > 0 && ` No latency of its own: ${untimed.map((m) => m.arm_label).join(", ")}.`}
        </p>
      )}
    </>
  );
}

// Q5 of the Trust Report. A null block means the registered study is not scored yet.
export function DetectorSection({ d }) {
  const title = "Trained detector vs the phrase list";
  if (!d) {
    return (
      <Section title={title}>
        <p className="border-l-2 border-app-border-strong pl-3 text-sm text-app-muted">
          Registered before training (<code className="inline-code">evals/validation/v1/PREREG_detector_v1.md</code>),
          not yet scored.
        </p>
      </Section>
    );
  }
  const r = d.primary?.injecagent_recall;
  const f = d.primary?.shipped_fpr;
  const dec = d.decision || {};
  const absent = d.absent || [];
  const unscored = (d.unscored || []).filter((u) => u.unscored > 0);
  return (
    <Section title={title}>
      <p className="mb-3 text-sm text-app-muted">
        A small CPU classifier given the request, the tool name and the tool result in one frame. The
        leave-one-source-out arm scores each source with the fold model trained without it; a row marked in-source
        was scored by a model that trained on that source. Pre-registered, scored once on sealed rows
        {d.seal_digest ? ` (seal ${d.seal_digest.slice(0, 12)})` : ""}.
      </p>
      {/* Every count, rate and latency column in mono, including the "–" of a source without positives. */}
      <DataTable
        numeric={[2, 3, 4, 5, 6]}
        head={["Source", "Arm", "Injected texts flagged", "Benign texts flagged", "Distinct benign", "AUROC", "p50 latency"]}
        rows={(d.rows || []).map((x) => [
          x.source_label,
          x.in_source ? `${x.arm_label} (in-source)` : x.arm_label,
          flagged(x.tp, x.n_pos, x.recall),
          flagged(x.fp, x.n_neg, x.fpr),
          x.n_neg ? x.distinct_neg : "–",
          x.auroc === null || x.auroc === undefined ? "–" : x.auroc.toFixed(2),
          ms(x.p50_ms),
        ])}
      />
      <p className="mt-3 text-xs text-app-subtle">
        Decision: {dec.adopt ? "adopted as an observe-only signal" : "not adopted; the detector stays dev-only"}.
        {r &&
          ` Unspent InjecAgent results, fold that never saw InjecAgent: ${r.tp} of ${r.n} flagged, ${interval1(r)} (bar at least ${pct(dec.min_recall)}).`}
        {f &&
          ` Shipped model on ${f.n} distinct benign tool results: ${f.fp} of ${f.n} flagged, ${interval1(f)} (bar at most ${pct(dec.max_fpr)}).`}
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Unscored rows (no finite score, excluded from rates):{" "}
        {unscored.length ? unscored.map((u) => `${u.label} ${u.unscored} of ${u.n_rows}`).join("; ") : "none"}.
      </p>
      {absent.length > 0 && (
        <p className="mt-1 text-xs text-app-subtle">Registered arms not run: {absent.map((a) => a.label).join(", ")}.</p>
      )}
      <p className="mt-1 text-xs text-app-subtle">
        No adaptive-attack evaluation. deepset is in-distribution; AgentDojo is dev-only and not scored here.
        Leave-one-source-out recall is the only generalisation claim; the shipped model's false-positive rate and the
        baselines' rows are registered measurements on the sealed rows and say nothing about unseen sources.
        InjecAgent's 62 attacker instructions and 17 tool-result templates appear in both the training and the scored
        rows.
      </p>
      {d.secondaries && <SecondariesBlock s={d.secondaries} />}
    </Section>
  );
}

// Q6 of the Trust Report: the registered judge-accuracy result on tool trajectories (PREREG_q1_toolloop.md).
export function ToolloopSection({ t }) {
  const checks = t.checks || [];
  const dec = t.decision || {};
  const per = Object.entries(dec.per_check || {});
  // The registered bar per check; one phrase when every check has the same bar.
  const barOf = (c) => {
    const acc = c.floor.accuracy.toFixed(2);
    const f1 = c.floor.f1.toFixed(2);
    const floor = acc === f1 ? `accuracy and F1 at least ${acc}` : `accuracy at least ${acc} and F1 at least ${f1}`;
    return `${floor}, at most ${pct(c.max_unscored_rate)} of questions unanswered`;
  };
  const bars = per.map(([k, c]) => [k, barOf(c)]);
  const bar = new Set(bars.map(([, b]) => b)).size === 1
    ? bars[0][1]
    : bars.map(([k, b]) => `${(CHECK_NAMES[k] || k).toLowerCase()}: ${b}`).join("; ");
  const missed = per.filter(([, c]) => !c.meets).map(([k, c]) => `${(CHECK_NAMES[k] || k).toLowerCase()}: ${c.reason}`);
  const balanced = checks.length > 0 && checks.every((c) => c.positives === checks[0].positives && c.negatives === c.positives);
  const n = balanced
    ? `n = ${checks[0].positives} per class per check`
    : `n = ${checks.map((c) => `${(CHECK_NAMES[c.check] || c.check).toLowerCase()} ${c.positives} positive and ${c.negatives} negative`).join("; ")}`;
  const ceiling = checks.length > 0 && checks.every((c) => c.accuracy?.point === 1);
  const low = Math.min(...checks.map((c) => c.accuracy?.low ?? 1));
  return (
    <Section title="Judge accuracy on tool trajectories">
      <p className="mb-3 text-sm text-app-muted">
        {graderName(t.grader)} host subagents graded the sealed blind split of gold v2, multi-step tool trajectories
        labelled by deterministic oracles, one accepted answer per question. Pre-registered
        {t.seal_digest ? ` (seal ${t.seal_digest.slice(0, 12)})` : ""}.
      </p>
      <DataTable
        numeric={[1, 2, 3, 4, 5, 6]}
        head={["Check", "n (unanswered)", "Accuracy", "Recall", "Specificity", "F1", "κ"]}
        rows={checks.map((c) => [
          CHECK_NAMES[c.check] || c.check,
          `${c.n} (${c.unanswered})`,
          interval(c.accuracy),
          interval(c.recall),
          interval(c.specificity),
          c.f1.toFixed(2),
          c.kappa.toFixed(2),
        ])}
      />
      <p className="mt-3 text-xs text-app-subtle">
        {dec.claim_allowed
          ? `Decision: the claim is allowed; both checks meet the registered bar (${bar}).`
          : `Decision: the claim is not allowed (${missed.join("; ")}), so no accuracy on tool trajectories is claimed.`}
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Gold written by Sonnet subagents, the grader&apos;s vendor. The authors were blind to the rubric, the judge prompt,
        gold v1 and the probe corpus, but wrote to the oracle&apos;s own rules with the intended label in mind, so the set
        measures agreement with that rule on clean, deliberately constructed cases (including hard negatives that quote
        the instruction and decline), not on ambiguous ones. The answer key was in the repository during grading; the graders were told to read only the
        task JSON, and a post-hoc audit of their transcripts found only the two CLI commands and their own scratch files,
        so the guarantee is procedural, not technical. Two checks only; static authored trajectories, not a model&apos;s
        own replies, so no 7-8B target behaviour is measured here.{" "}
        {ceiling
          ? `${n}, so a result at the ceiling carries a lower bound of ${pct(low)} and says nothing finer.`
          : `${n}; read the intervals, not the points.`}
      </p>
    </Section>
  );
}

// Q7 of the Trust Report: the registered judge-accuracy result under the version-3 wording (PREREG_q7_claims_v3.md):
// gold v3 (claimed-but-uncalled actions, pasted tool-result secrets) plus the gold v2 blind split re-asked under it.
export function ClaimsV3Section({ c }) {
  const checks = c.checks || [];
  const dec = c.decision || {};
  const per = Object.entries(dec.per_check || {});
  const floors = new Set(per.map(([, v]) => `${v.floor.accuracy.toFixed(2)}/${v.floor.f1.toFixed(2)}`));
  const [acc, f1] = (floors.values().next().value || "0.60/0.60").split("/");
  const bar = `accuracy ${acc === f1 ? `and F1 at least ${acc}` : `at least ${acc} and F1 at least ${f1}`} on the pooled items and on gold v3 alone`;
  const missed = per.filter(([, v]) => !v.meets).map(([k, v]) => `${(CHECK_NAMES[k] || k).toLowerCase()}: ${v.reason}`);
  const rows = [];
  for (const ch of checks) {
    const label = CHECK_NAMES[ch.check] || ch.check;
    const subsets = [["pooled", ch], ["gold v3", ch.subsets?.gold_v3], ["gold v2", ch.subsets?.gold_v2]].filter(([, b]) => b);
    for (const [items, b] of subsets) {
      rows.push([`${label}, ${items}`, `${b.n} (${b.unanswered})`, interval(b.accuracy), interval(b.recall),
        interval(b.specificity), b.f1.toFixed(2), b.kappa.toFixed(2)]);
    }
  }
  const n = checks
    .filter((ch) => ch.subsets?.gold_v3)
    .map((ch) => `${(CHECK_NAMES[ch.check] || ch.check).toLowerCase()} ${ch.subsets.gold_v3.positives} positive and ${ch.subsets.gold_v3.negatives} negative`)
    .join("; ");
  return (
    <Section title="Judge accuracy under the version-3 wording">
      <p className="mb-3 text-sm text-app-muted">
        {graderName(c.grader)} host subagents graded, under judge prompt version {c.judge_prompt_version}, the sealed blind
        split of gold v3 (claimed-but-uncalled actions and pasted tool-result secrets, labelled by deterministic oracles)
        and the gold v2 blind split re-asked under the same wording, one accepted answer per question. Pre-registered
        {c.seal_digest ? ` (seal ${c.seal_digest.slice(0, 12)})` : ""}.
      </p>
      <DataTable
        numeric={[1, 2, 3, 4, 5, 6]}
        head={["Check", "n (unanswered)", "Accuracy", "Recall", "Specificity", "F1", "κ"]}
        rows={rows}
      />
      <p className="mt-3 text-xs text-app-subtle">
        {dec.claim_allowed
          ? `Decision: the claim is allowed; both checks meet the registered bar (${bar}), so version 3 is the default judge prompt.`
          : `Decision: the claim is not allowed (${missed.join("; ")}), so no accuracy under the version-3 wording is claimed and the default judge prompt stays at version 2.`}
      </p>
      <p className="mt-1 text-xs text-app-subtle">
        Gold v3 written by Sonnet subagents, the grader&apos;s vendor, blind to the rubric, the judge prompt, gold v1, gold v2
        and the probe corpus, to the oracles&apos; own rules with the intended label in mind; offers, denials, quoted
        instructions and benign controls are the hard negatives. The graders were told to read only the task JSON and
        their transcripts were audited afterwards, so the guarantee is procedural, not technical. Two checks only; static
        authored trajectories, not a model&apos;s own replies. On gold v3, n = {n}; read the intervals, not the points.
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

      {evidence.step5_binding && <Step5Section s={evidence.step5_binding} />}

      {evidence.guard_vs_detectors && <DetectorsStudySection s={evidence.guard_vs_detectors} />}

      {evidence.content_safety && <ContentSafetySection s={evidence.content_safety} />}

      <DetectorSection d={evidence.detector} />

      {evidence.toolloop && <ToolloopSection t={evidence.toolloop} />}

      {evidence.claims_v3 && <ClaimsV3Section c={evidence.claims_v3} />}

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
