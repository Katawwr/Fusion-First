import React from "react";
import content from "../../content/integrations.json";
import { Code, Inline } from "./index";

// Commands and spec strings come from integrations.json, which tests/test_docs_commands.py parses with
// the real CLI.

export function Steps({ steps }) {
  return steps.map((step) => (
    <div key={step.label}>
      <p className="mb-1.5 text-sm text-app-muted">
        <Inline text={step.label} />
      </p>
      <Code code={step.code} label={step.lang} />
    </div>
  ));
}

export function TargetsTable() {
  return (
    <>
      <dl className="deflist">
        {content.targets.map((t) => (
          <React.Fragment key={t.spec}>
            <dt>{t.name}</dt>
            <dd>
              <code className="inline-code text-app-text">{t.spec}</code>
              {t.note && (
                <p className="mt-1 text-sm">
                  <Inline text={t.note} />
                </p>
              )}
            </dd>
          </React.Fragment>
        ))}
      </dl>
      <p className="table-note mt-5">
        <Inline text={content.grader} />
      </p>
    </>
  );
}

// The first local step and the targets table (the overview's short form of /use#local).
export default function RunLocally() {
  const local = content.sections.find((s) => s.id === "local");
  return (
    <div className="flex flex-col gap-5">
      <Steps steps={local.steps.slice(0, 1)} />
      <TargetsTable />
    </div>
  );
}
