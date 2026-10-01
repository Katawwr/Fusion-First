import React from "react";
import content from "../../content/integrations.json";
import { Code } from "./index";

// "Run it locally": the web app on your machine, then the target you point it at. The commands and
// spec strings come from integrations.json, which tests/test_docs_commands.py parses with the real CLI.
export function TargetsTable() {
  return (
    <>
      <ul className="target-list">
        {content.targets.map((t) => (
          <li key={t.spec}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <span className="font-medium text-app-text">{t.name}</span>
              <span className="eyebrow">Scan: {t.scan}</span>
            </div>
            <code className="inline-code mt-1.5 inline-block">{t.spec}</code>
            <p className="mt-1.5 text-sm text-app-muted">
              {t.cost}
              {t.also && <span className="mt-1 block text-app-subtle">{t.also}</span>}
            </p>
          </li>
        ))}
      </ul>
      <p className="table-note">{content.grader}</p>
    </>
  );
}

export default function RunLocally({ compact = false }) {
  const local = content.sections.find((s) => s.id === "local");
  const steps = compact ? local.steps.slice(0, 1) : local.steps;
  return (
    <div className="flex flex-col gap-5">
      {steps.map((step) => (
        <div key={step.label}>
          <p className="mb-1.5 text-sm text-app-muted">{step.label}</p>
          <Code code={step.code} label={step.lang} />
        </div>
      ))}
      <TargetsTable />
    </div>
  );
}
