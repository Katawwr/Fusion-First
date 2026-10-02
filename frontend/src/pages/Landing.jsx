import React from "react";
import { Helmet } from "react-helmet-async";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import evidence from "../content/evidence.json";
import { Doc, DocHeader, DocSection, IntervalStrip } from "../components/doc";
import RunLocally from "../components/doc/RunLocally";
import { interval, points } from "../lib/evidence";
import { findings, headlineStats, limitations, resultGroups } from "../lib/overview";

// Every number is rendered from the generated evidence (content/evidence.json); the page source carries none.

const TITLE = "Fusion First: Measure and guard AI agents";
const SUMMARY =
  "Attack your AI agent, grade safety and quality with a grader measured in every run, and guard it at runtime. Built for open-weight models.";

function estimate(row) {
  return row.scale === "diff" ? points(row.est) : interval(row.est);
}

export function ResultsTable({ groups }) {
  if (!groups.length) return <p className="text-app-muted">No committed results yet.</p>;
  return (
    <figure>
      <figcaption className="fig-caption">
        <b>Table 1.</b> Committed results with 95% intervals, pre-registered where marked. The bar is the interval; the tick is the estimate.
      </figcaption>
      <div className="table-frame">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Measure</th>
              <th scope="col" className="text-right">
                n
              </th>
              <th scope="col">Estimate (95% CI)</th>
              <th scope="col" className="hide-narrow">
                Interval
              </th>
            </tr>
          </thead>
          {groups.map((g) => (
            <tbody key={g.id}>
              <tr className="group">
                <td colSpan={4}>
                  <span className="block font-semibold text-app-text">{g.title}</span>
                  <span className="mt-0.5 block text-xs text-app-subtle">{g.note}</span>
                </td>
              </tr>
              {g.rows.map((r) => (
                <tr key={r.label}>
                  <td>
                    {r.label}
                    {r.detail && <span className="block text-xs text-app-subtle">{r.detail}</span>}
                  </td>
                  <td className="num text-right text-app-muted">{r.n}</td>
                  <td className="num">{estimate(r)}</td>
                  <td className="hide-narrow" style={{ verticalAlign: "middle" }}>
                    <IntervalStrip est={r.est} scale={r.scale} tone={r.tone} label={`${r.label}: ${estimate(r)}`} />
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      <p className="table-note">
        Purple: Fusion&apos;s results. Pink: costs. Grey: comparators, null results and graders below the floor.
        Change rows span ±50 points.
      </p>
    </figure>
  );
}

function HeadlineStats({ stats }) {
  if (!stats.length) return null;
  return (
    <figure className="headline-stats">
      <dl>
        {stats.map((s) => (
          <div key={s.label} className={s.muted ? "headline-stat headline-stat--muted" : "headline-stat"}>
            <dt>{s.label}</dt>
            <dd>
              <span className="headline-value">{s.value}</span>
              <span className="headline-note">{s.note}</span>
            </dd>
          </div>
        ))}
      </dl>
    </figure>
  );
}

export default function Landing() {
  const stats = headlineStats(evidence);
  const groups = resultGroups(evidence);
  const facts = findings(evidence);
  const limits = limitations(evidence);
  return (
    <>
      <Helmet>
        <title>{TITLE}</title>
        <meta
          name="description"
          content="Fusion First attacks your AI agent, grades safety and quality with a grader whose accuracy is measured in every run, and adds a runtime guard that redacts secrets and blocks tool calls the user did not ask for. Every rate carries a 95% interval. Built for open-weight models."
        />
        <meta
          name="keywords"
          content="AI agent evaluation, LLM safety testing, LLM quality evals, prompt injection testing, OWASP LLM Top 10, agentic AI security, open-weight model testing, Ollama, LLM red teaming, AI guardrails, instruction following"
        />
        <meta property="og:title" content={TITLE} />
        <meta property="og:description" content={SUMMARY} />
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://fusion-first-testing.com" />
        <meta
          property="og:image"
          content="https://fusion-first-testing.com/og-image.png"
        />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={TITLE} />
        <meta name="twitter:description" content={SUMMARY} />
        <link rel="canonical" href="https://fusion-first-testing.com" />
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            name: "Fusion First",
            description:
              "Safety and quality evaluation and a runtime guard for AI agents. Attacks the agent, grades the transcripts with a grader whose accuracy is measured, and at runtime redacts leaked secrets and blocks unrequested tool calls. Built for open-weight models.",
            applicationCategory: "DeveloperApplication",
            operatingSystem: "Windows, macOS, Linux",
            offers: {
              "@type": "Offer",
              price: "0",
              priceCurrency: "USD",
              description: "Free demo scan; free local testing of your own open-weight models",
            },
          })}
        </script>
      </Helmet>

      <Doc wide>
        <DocHeader title="Measured evaluation and a runtime guard for AI agents">
          <p>
            Fusion First tests an agent with OWASP-mapped attacks and ordinary tasks, grades safety and quality, and
            reports each rate with a 95% interval and the grader&apos;s measured accuracy. A runtime guard redacts
            secrets and blocks tool calls the user did not ask for.
          </p>
          <div className="mt-6 flex flex-wrap gap-2.5">
            <Link to="/scan" className="action action--primary">
              Run Demo
            </Link>
            <Link to="/use#local" className="action">
              Run Locally
            </Link>
            <Link to="/trust" className="action">
              Evidence
              <ArrowRight size={15} aria-hidden />
            </Link>
          </div>
          <HeadlineStats stats={stats} />
        </DocHeader>

        <DocSection id="method" title="Method">
          <dl className="deflist">
            <dt>Measured grader</dt>
            <dd>
              By default Claude grades open-weight targets, a different model family. Each run includes blind
              known-answer questions and checks the grader against deterministic oracles on its own clear-cut
              transcripts. If the grader misses the policy floor, denies a violation the oracles confirm, or leaves
              questions unanswered, the grade is withheld (<code className="inline-code">?</code>); rates stay visible.
            </dd>
            <dt>Pre-registered tests</dt>
            <dd>
              For the guard and the rubric comparison, hypothesis, metric and decision rule were committed before
              scoring; results were scored once and compared with paired McNemar tests. A missed rule is reported as
              missed.
            </dd>
            <dt>Runtime guard</dt>
            <dd>
              Redacts secrets and PII in replies and blocks system-prompt dumps. A tool call that is not a read runs
              only if the user&apos;s own request covers it; sends to non-allowlisted destinations are blocked. Given
              the tool results, it also blocks a read they ask for, and the user did not, when they also ask to send
              data out.
            </dd>
            <dt>Prompt fix (optional)</dt>
            <dd>A policy block appended to the system prompt and re-tested on your model. See the negative results.</dd>
          </dl>
        </DocSection>

        <DocSection id="results" title="Results">
          <ResultsTable groups={groups} />
          {facts.length > 0 && (
            <ol className="mt-6 flex list-decimal flex-col gap-2 pl-5 text-[0.95rem] leading-relaxed text-app-text marker:text-app-subtle">
              {facts.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ol>
          )}
        </DocSection>

        <DocSection id="limitations" title="Limitations">
          <ul className="flex list-disc flex-col gap-2 pl-5 text-[0.95rem] leading-relaxed text-app-muted marker:text-app-subtle">
            {limits.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </DocSection>

        <DocSection
          id="run-locally"
          title="Run Locally"
          lead="This site's demo replays recorded responses. Locally, the same app tests a live model."
        >
          <RunLocally compact />
          <p className="mt-5 text-sm">
            <Link to="/use" className="text-link">
              Plugin, command line, guard, MCP and CI
            </Link>
          </p>
        </DocSection>
      </Doc>
    </>
  );
}
