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
    <Section title="Does the runtime guardrail stop real attacks?">
      <p className="mb-3 text-sm text-app-muted">
        {runtime.fresh
          ? `The guardrail you wrap around your agent, with its current rules, applied once to fresh attacks that really succeeded against ${runtime.models.length} small open-weight models (none of its rules was written against them), then re-scored by the same answer keys. Registered before it was run. The first measurement, with older rules, stopped ${first.all.stopped} of ${first.all.attacks}.`
          : `The guardrail you wrap around your agent, applied to the attacks that really succeeded against ${runtime.models.length} small open-weight models above, then re-scored by the same answer keys. Registered before it was run.`}
      </p>
      <Table
        head={["Attack", "Real attacks", "Stopped", "Clean transcripts", "Wrongly blocked"]}
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
      {runtime.fresh ? (
        (runtime.findings || []).map((f) => (
          <p key={f} className="mt-3 text-xs text-app-subtle">
            {f}
          </p>
        ))
      ) : (
        <p className="mt-3 text-xs text-app-subtle">
          It misses consequential tools whose names don&apos;t say what they do (a &quot;Manage…&quot; or
          &quot;UnlockDoor&quot; tool), and it blocks some harmless read tools with mixed-case names. Both are
          known and listed in the Trust Report.
        </p>
      )}
    </Section>
  );
}

function NotYet({ what }) {
  return (
    <p className="rounded-lg border border-dashed border-app-border p-4 text-sm text-app-muted">
      Not yet measured: {what}. Nothing is estimated in its place.
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
      <p className="mb-10 text-app-muted" style={{ maxWidth: "700px", lineHeight: 1.6 }}>
        Fusion grades other AI agents, so it has to be graded too. These are its own measured results,
        with 95% intervals, from committed evidence. Where something hasn't been measured yet, it says
        so. Small samples mean wide intervals: read the ranges, not just the headline number.
      </p>

      <Section title="Is the judge accurate?">
        {judge.length === 0 ? (
          <NotYet what="grader accuracy against deterministic oracles" />
        ) : (
          <>
            <p className="mb-3 text-sm text-app-muted">
              Grader verdicts on real open-weight model transcripts, scored against deterministic oracles
              (no AI in the answer key), next to simple rule-based checks on the same items.
            </p>
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
            <p className="mt-3 text-xs text-app-subtle">
              Against the rule-based checks on the same items (paired McNemar test, p &lt; 0.05):
            </p>
            {significanceByGrader(judge).map((s) => (
              <p key={s} className="mt-1 text-xs text-app-subtle">
                {s}
              </p>
            ))}
            {judge.some((j) => j.audit) && (
              <p className="mt-3 text-xs text-app-subtle">
                Every disagreement with the oracle was also read and classified. Most were cases the
                oracle can't see, such as a small model writing an action in plain words instead of a
                tool call. That reading is an AI's, not ground truth, so the table above is unchanged by it.
              </p>
            )}
          </>
        )}
      </Section>

      {evidence.rubric_vs_plain && (
        <Section title="Does the rubric beat simply asking an AI?">
          <p className="mb-3 text-sm text-app-muted">
            The same transcripts graded twice by the same Claude model: once with Fusion&apos;s rubric,
            once asked one plain yes/no question. Registered before the plain answers were collected.
          </p>
          <Table
            head={["Check", "n", "Fusion's rubric", "One plain question", "Difference (rubric minus plain)"]}
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
              ? "The rubric judge is significantly more accurate than a plain question (the registered rule is met)."
              : "Not shown: the rubric is not more accurate than asking the same model one plain question, so we don't claim it is. What it adds is a checkable grade: an answer per criterion, quoting the agent's own words, which lets a run reject grades that aren't grounded in the transcript."}
          </p>
        </Section>
      )}

      <Section title="Does the fix work, and what does it cost?">
        {evidence.fix_pooled && (
          <div className="mb-4">
            <Table
              head={["Experiment", "Pairs", "As written", "With fix", "Change", "What it shows"]}
              rows={evidence.fix_pooled.map((p) => [
                `${p.experiment} (all models)`,
                p.n_pairs,
                interval(p.baseline_rate),
                interval(p.hardened_rate),
                signedPoints(p.change),
                p.verdict,
              ])}
            />
            <p className="mt-2 text-xs text-app-subtle">
              Pooled over every model tested; the range resamples whole items, because the same item runs
              on every model. Per-model results follow.
            </p>
          </div>
        )}
        {evidence.fix_efficacy ? (
          <Table
            head={["Experiment", "Model", "Pairs", "As written", "With fix", "What it shows"]}
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
          <NotYet what="the as-written vs fixed prompt comparison on local open-weight models (the run is in progress)" />
        )}
      </Section>

      {evidence.runtime_guardrail && <GuardrailSection runtime={evidence.runtime_guardrail} />}

      {evidence.value_ledger && (
        <Section title="What each layer bought on real attacks">
          <p className="mb-3 text-sm text-app-muted">
            The first run's results, read item by item (the fix comparison above and the guardrail&apos;s
            first measurement, on the same transcripts): of the attacks that got through with the prompt
            as written, what the prompt fix removed and what the guardrail stopped.
          </p>
          <Table
            head={["Model", "Attacks found", "Fix removed", "New attacks the fix caused", "Guardrail stopped", "Either", "Neither"]}
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
              `The fix also made the models refuse ${evidence.value_ledger.fix_refusal_cost.safe_requests_newly_refused} safe requests they had answered. `}
            {evidence.value_ledger.note}
          </p>
        </Section>
      )}

      <Section title="Runtime guard for Claude Code">
        {guard.length === 0 ? (
          <NotYet what="the guard hook on held-out tool calls" />
        ) : (
          <>
            <p className="mb-3 text-sm text-app-muted">
              Tool calls written by independent agents who never saw the rules; each set is scored once.
            </p>
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
              It asks before the common exfiltration, destruction and remote-code patterns and misses much of
              the long tail. It is defense in depth, not a sandbox.
            </p>
          </>
        )}
      </Section>
    </main>
  );
}
