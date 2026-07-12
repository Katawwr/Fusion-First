import React from 'react';

// The harden diff is always "your prompt, unchanged + our guard block appended", so we render the
// original dim and the added guardrail block highlighted green — no diff library needed.
export default function DiffView({ original, guardBlock }) {
  return (
    <div className="overflow-hidden rounded-lg border border-app-border bg-surface-2">
      <pre className="max-h-96 overflow-auto p-3 text-xs leading-relaxed">
        <code className="text-app-subtle">{original.replace(/\n+$/, '')}</code>
        {'\n\n'}
        <code className="block rounded bg-emerald-500/10 text-emerald-200">
          {guardBlock.split('\n').map((line, i) => (
            <span key={i} className="block">
              <span className="select-none text-emerald-400/70">+ </span>
              {line}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}
