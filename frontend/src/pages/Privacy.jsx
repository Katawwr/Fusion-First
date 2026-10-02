import React from "react";
import { Helmet } from "react-helmet-async";
import { Doc, DocHeader, DocSection } from "../components/doc";

// Keep in sync with the real data flows: fusion_first/web (in-memory scan store), app/ (the hosted demo
// attaches no provider keys), fusion_first/backends (local-only live backends), src/lib/session.js.

export default function Privacy() {
  return (
    <>
      <Helmet>
        <title>Privacy &amp; Terms | Fusion First</title>
        <meta
          name="description"
          content="How Fusion First handles your prompts: no accounts, payments or analytics. Live testing runs on your machine."
        />
        <meta property="og:title" content="Privacy & Terms | Fusion First" />
        <meta
          property="og:description"
          content="No accounts, payments or analytics. Live testing runs on your machine."
        />
        <meta property="og:type" content="website" />
        <link rel="canonical" href="https://fusion-first-testing.com/privacy" />
      </Helmet>

      <Doc>
        <DocHeader title="Privacy & Terms" />

        <DocSection id="privacy" title="Privacy">
          <dl className="deflist">
            <dt>Demo scan on this site</dt>
            <dd>
              Your prompt is sent to the Fusion server, never to a model: the responses are recorded. Reports are
              held in server memory only (no database) and lost on restart.
            </dd>
            <dt>Local use</dt>
            <dd>
              The command line, MCP server and local web app store prompts and results only on your machine. What
              leaves it depends on the backends you choose: an Ollama target stays local; the{" "}
              <code className="inline-code">claude-cli</code> grader (the web app&apos;s default) sends transcripts,
              including your prompt, to Anthropic under your Claude subscription; a hosted target sends them to its
              provider and needs your key and <code className="inline-code">FUSION_ALLOW_API_SPEND=1</code>. Each
              provider&apos;s terms apply.
            </dd>
            <dt>Your browser</dt>
            <dd>
              Your theme choice (localStorage) and your last scan&apos;s prompt and report, so a refresh keeps them
              (sessionStorage, cleared when the tab closes). Fonts load from Google Fonts. No cookies, analytics or tracking.
            </dd>
            <dt>Training</dt>
            <dd>Fusion trains no model on your prompts or results.</dd>
          </dl>
        </DocSection>

        <DocSection id="terms" title="Terms">
          <dl className="deflist">
            <dt>No guarantees</dt>
            <dd>
              Fusion measures attack rates and grader accuracy, each with its uncertainty. It does not guarantee
              that grades are correct, that the guard or the prompt fix stops every attack, or that untested
              attacks and future model versions behave as measured. You remain responsible for testing, monitoring
              and human oversight of your AI systems.
            </dd>
            <dt>Acceptable use</dt>
            <dd>Test only AI systems you own or have explicit permission to test.</dd>
            <dt>Liability</dt>
            <dd>
              Fusion First is provided &quot;as is&quot;, without warranties. We are not liable for damages arising
              from its use or from changes you make based on its results.
            </dd>
            <dt>Changes</dt>
            <dd>We may update these terms; continued use means you accept the updated terms.</dd>
          </dl>
        </DocSection>

        <DocSection id="contact" title="Contact">
          <p className="text-[0.95rem] text-app-muted">
            Privacy, terms or safety:{" "}
            <a href="mailto:support-fusion@proton.me" className="text-link">
              support-fusion@proton.me
            </a>
          </p>
          <p className="mt-2 text-sm text-app-subtle">Last updated: October 2026</p>
        </DocSection>
      </Doc>
    </>
  );
}
