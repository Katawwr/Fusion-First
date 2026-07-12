import React from 'react';
import { checkMeta } from '../../lib/jargon';

// Newest-first stream of judged attacks. "Resisted" (green) or "Fooled" (red) at baseline —
// the "oh no, it really did that" moment. Uses the baseline arm (the raw prompt under attack).
export default function AttackFeedRow({ outcome }) {
  const meta = checkMeta(outcome.check);
  const fooled = outcome.baseline_issue;
  return (
    <div className="flex items-start gap-3 border-b border-app-border py-2 text-sm">
      <span className="mt-0.5 text-base" aria-hidden>
        {meta.icon}
      </span>
      <span className="flex-1 text-app-muted">{outcome.attack_label}</span>
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
          fooled ? 'bg-red-500/20 text-red-200' : 'bg-emerald-500/20 text-emerald-200'
        }`}
      >
        {fooled ? 'Fooled' : 'Resisted'}
      </span>
    </div>
  );
}
