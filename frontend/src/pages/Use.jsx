import React from "react";
import { Helmet } from "react-helmet-async";
import { Link } from "react-router-dom";
import content from "../content/integrations.json";
import { Doc, DocHeader } from "../components/doc";
import { Steps, TargetsTable } from "../components/doc/RunLocally";

// Every command here is parse-tested against the CLI (tests/test_docs_commands.py reads the same JSON).
export default function Use() {
  return (
    <Doc>
      <Helmet>
        <title>Use Fusion | Fusion First</title>
        <meta
          name="description"
          content="Run Fusion First locally: web app, Claude Code plugin, command line, runtime guard, MCP server and CI."
        />
      </Helmet>
      <DocHeader title="Use Fusion" />

      <nav aria-label="On this page" className="mt-7 flex flex-wrap gap-x-3.5 gap-y-1.5 whitespace-nowrap text-[0.8125rem]">
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
            <Steps steps={s.steps} />
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
        Without installing anything: the{" "}
        <Link to="/scan" className="text-link">
          demo scan
        </Link>{" "}
        (recorded responses).
      </p>
    </Doc>
  );
}
