import React from "react";
import { Helmet } from "react-helmet-async";
import { Link } from "react-router-dom";
import CodeSnippet from "../components/fix/CodeSnippet";
import content from "../content/integrations.json";

// How to run Fusion for real: every command here is parse-tested against the CLI
// (tests/test_docs_commands.py reads this same JSON), so the page can't drift from the tool.
export default function Use() {
  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "clamp(2rem, 6vw, 3.5rem) 1rem" }}>
      <Helmet>
        <title>Use Fusion | Fusion First</title>
      </Helmet>
      <h1 style={{ fontSize: "clamp(1.8rem, 5vw, 2.6rem)", margin: "0 0 0.75rem", color: "var(--text)" }}>
        Use Fusion
      </h1>
      <div style={{ height: "1.25rem" }} />
      <nav aria-label="On this page" className="mb-8 flex flex-wrap gap-2">
        {content.sections.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="rounded-full border border-app-border px-3 py-1 text-sm text-app-muted hover:text-app-text"
          >
            {s.title}
          </a>
        ))}
      </nav>
      <div className="flex flex-col gap-10">
        {content.sections.map((s) => (
          <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} style={{ scrollMarginTop: "5rem" }}>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h2 id={`${s.id}-title`} className="text-xl font-semibold text-app-text" style={{ margin: 0 }}>
                {s.title}
              </h2>
              {s.badge && (
                <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-app-muted">
                  {s.badge}
                </span>
              )}
            </div>
            <div className="flex flex-col gap-3">
              {s.steps.map((step) => (
                <div key={step.label}>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-app-subtle">{step.label}</p>
                  <CodeSnippet code={step.code} language={step.lang} />
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
      <p className="mt-12 text-sm text-app-muted">
        <Link to="/scan" className="underline">Run the demo scan</Link>
      </p>
    </main>
  );
}
