import React from "react";
import { Helmet } from "react-helmet-async";
import { Link } from "react-router-dom";
import content from "../content/integrations.json";
import { Code, Doc, DocHeader } from "../components/doc";
import { TargetsTable } from "../components/doc/RunLocally";

// How to run Fusion for real: every command here is parse-tested against the CLI
// (tests/test_docs_commands.py reads this same JSON), so the page can't drift from the tool.
export default function Use() {
  return (
    <Doc>
      <Helmet>
        <title>Use Fusion | Fusion First</title>
      </Helmet>
      <DocHeader eyebrow="Use" title="Use Fusion" />

      <nav aria-label="On this page" className="mt-7 flex flex-wrap gap-x-4 gap-y-1.5 text-sm">
        {content.sections.map((s) => (
          <a key={s.id} href={`#${s.id}`} className="text-app-muted underline-offset-4 hover:text-app-text hover:underline">
            {s.title}
          </a>
        ))}
      </nav>

      {content.sections.map((s) => (
        <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} className="doc-section">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 id={`${s.id}-title`} className="doc-h2">
              {s.title}
            </h2>
            {s.badge && <span className="eyebrow">{s.badge}</span>}
          </div>
          <div className="mt-5 flex flex-col gap-5">
            {s.steps.map((step) => (
              <div key={step.label}>
                <p className="mb-1.5 text-sm text-app-muted">{step.label}</p>
                <Code code={step.code} label={step.lang} />
              </div>
            ))}
            {s.id === "local" && (
              <div>
                <h3 className="doc-h3 mb-3">Targets</h3>
                <TargetsTable />
              </div>
            )}
          </div>
        </section>
      ))}

      <p className="doc-section text-sm text-app-muted">
        No install:{" "}
        <Link to="/scan" className="text-link">
          demo scan
        </Link>{" "}
        (recorded responses).
      </p>
    </Doc>
  );
}
