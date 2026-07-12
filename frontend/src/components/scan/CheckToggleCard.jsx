import React from 'react';
import Term from '../ui/Term';
import OwaspChip from '../report/OwaspChip';
import { checkMeta } from '../../lib/jargon';

// A safety check framed as a plain question, with the real OWASP term in a tooltip. Toggleable.
export default function CheckToggleCard({ check, enabled, onToggle }) {
  const meta = checkMeta(check);
  return (
    <button
      type="button"
      onClick={() => onToggle(check)}
      className={`flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-all ${
        enabled
          ? 'border-fusion-cyan bg-fusion-cyan-light'
          : 'border-app-border bg-app-elev opacity-70 hover:opacity-100'
      }`}
    >
      <span className="text-2xl" aria-hidden>
        {meta.icon}
      </span>
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-app-text">{meta.label}</span>
          <Term term={meta.term} tip={meta.tip}>
            <OwaspChip tag={{ llm: meta.owasp.split(' · ')[0], asi: meta.owasp.split(' · ')[1] }} />
          </Term>
        </div>
        <p className="mt-1 text-sm text-app-muted">{meta.scenario}</p>
      </div>
      <span
        className={`mt-1 flex h-6 w-11 shrink-0 items-center rounded-full p-0.5 transition-colors ${
          enabled ? 'bg-fusion-cyan justify-end' : 'bg-surface-2 justify-start'
        }`}
      >
        <span className="h-5 w-5 rounded-full bg-white shadow" />
      </span>
    </button>
  );
}
