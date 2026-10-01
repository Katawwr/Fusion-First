import React from "react";
import { Helmet } from "react-helmet-async";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import evidence from "../content/evidence.json";
import { Doc, DocHeader, DocSection, IntervalStrip } from "../components/doc";
import RunLocally from "../components/doc/RunLocally";
import { interval, points } from "../lib/evidence";
import { findings, limitations, resultGroups } from "../lib/overview";

// The overview reads like a paper's abstract and results table. Every number is rendered from the
// generated evidence (content/evidence.json); the page source carries none.

function estimate(row) {
  return row.scale === "diff" ? points(row.est) : interval(row.est);
}

export function ResultsTable({ groups }) {
  if (!groups.length) return <p className="text-app-muted">No committed results yet.</p>;
  return (
    <figure>
      <figcaption className="fig-caption">
        <b>Table 1.</b> Pre-registered results with 95% intervals. Bars plot the interval; the tick is the estimate.
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
        Pink marks costs (wrong blocks, refusals, missed instructions); grey marks comparators. Change rows run from
        −50 to +50 points around zero.
      </p>
    </figure>
  );
}

export default function Landing() {
  const groups = resultGroups(evidence);
  const facts = findings(evidence);
  const limits = limitations(evidence);
  return (
    <>
      <Helmet>
        <title>Fusion First: Measure and guard AI agents</title>
        <meta
          name="description"
          content="Fusion First attacks your AI agent, grades safety and quality with a grader measured against known answers, and adds a runtime guardrail that blocks leaked secrets and tool calls the user didn't request. Every rate carries a confidence interval. Built for open-weight models."
        />
        <meta
          name="keywords"
          content="AI agent evaluation, LLM safety testing, LLM quality evals, prompt injection testing, OWASP LLM Top 10, agentic AI security, open-weight model testing, Ollama, Llama safety, LLM red teaming, AI guardrails, instruction following, safety report card"
        />
        <meta
          property="og:title"
          content="Fusion First: Measure and guard AI agents"
        />
        <meta
          property="og:description"
          content="Attack your AI agent, grade safety and quality with a measured grader, and guard it at runtime. Built for open-weight models."
        />
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://fusion-first-testing.com" />
        <meta
          property="og:image"
          content="https://fusion-first-testing.com/og-image.png"
        />
        <meta name="twitter:card" content="summary_large_image" />
        <meta
          name="twitter:title"
          content="Fusion First: Measure and guard AI agents"
        />
        <meta
          name="twitter:description"
          content="Attack your AI agent, grade safety and quality with a measured grader, and guard it at runtime. Built for open-weight models."
        />
        <link rel="canonical" href="https://fusion-first-testing.com" />
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            name: "Fusion First",
            description:
              "Safety and quality evaluation engine and runtime guardrail for AI agents. Attacks the agent, grades transcripts with a grader whose accuracy is measured, and blocks leaked secrets and unrequested tool calls at runtime. Built for open-weight models.",
            applicationCategory: "DeveloperApplication",
            operatingSystem: "Web",
            offers: {
              "@type": "Offer",
              price: "0",
              priceCurrency: "USD",
              description:
                "Free demo scan and local testing with your own open-weight models",
            },
          })}
        </script>
      </Helmet>

      <Doc wide>
        <DocHeader eyebrow="Technical overview" title="Measured evaluation and a runtime guard for AI agents">
          <p>
            Fusion First attacks an agent with OWASP-mapped prompts, grades the transcripts with a cross-family
            judge whose accuracy is measured against known answers in every run, and reports each rate with a 95%
            interval. A runtime guard redacts leaked secrets and blocks tool calls the user&apos;s own request does
            not cover; the results below come from pre-registered tests on open-weight models.
          </p>
          <div className="mt-6 flex flex-wrap gap-2.5">
            <Link to="/scan" className="action action--primary">
              Run the demo scan
            </Link>
            <Link to="/use#local" className="action">
              Run it locally
            </Link>
            <Link to="/trust" className="action">
              Full evidence
              <ArrowRight size={15} aria-hidden />
            </Link>
          </div>
        </DocHeader>

        <DocSection id="method" title="Method">
          <dl className="deflist">
            <dt>Cross-family judge</dt>
            <dd>
              Claude grades open-weight targets, so no model grades its own family. Each run seeds blind
              known-answer items and checks the grader against deterministic oracles on its own clear-cut
              transcripts; below the policy floor the grade is withheld (<code className="inline-code">?</code>),
              not guessed.
            </dd>
            <dt>Pre-registered tests</dt>
            <dd>
              Hypothesis, metric and decision rule are committed before scoring. Transcripts are fresh, scored once,
              and compared on the same items with paired McNemar tests. Rates carry 95% intervals; a result
              that misses its rule is reported as missed.
            </dd>
            <dt>Runtime guard</dt>
            <dd>
              Redacts secrets in replies, blocks system-prompt dumps, and, after untrusted content, allows a tool call
              only when the user&apos;s request covers it. Given the tool results as untrusted text, it also blocks a
              read paired with a send to an outside address.
            </dd>
            <dt>Prompt fix (optional)</dt>
            <dd>An appended policy block, re-tested on the user&apos;s own model; see the negative results.</dd>
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
          title="Run it locally"
          lead="This site runs a demo on recorded responses. On your machine the same app tests a live model: free with Ollama or your own server, or a hosted API billed to your own key."
        >
          <RunLocally compact />
          <p className="mt-5 text-sm">
            <Link to="/use#local" className="text-link">
              All setup options
            </Link>
            <span className="text-app-subtle"> · </span>
            <Link to="/use" className="text-link">
              Plugin, CLI, MCP and CI
            </Link>
          </p>
        </DocSection>
      </Doc>
    </>
  );
}
