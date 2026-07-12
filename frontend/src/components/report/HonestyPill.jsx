import React from 'react';
import { HONESTY } from '../../lib/jargon';

const TONE = {
  good: 'border-ok/45 bg-ok/12 text-ok',
  warn: 'border-warn/45 bg-warn/12 text-warn',
  bad: 'border-app-border-strong bg-surface-2 text-app-muted',
};

// The differentiator: translated but never softened. Keeps the real badge word (PROVEN/…) visible.
export default function HonestyPill({ badge, p, nPairs }) {
  const meta = HONESTY[badge] || HONESTY.INCONCLUSIVE;
  const stat =
    badge === 'PROVEN' && typeof p === 'number'
      ? ` (p=${p.toFixed(3)}${nPairs ? `, ${nPairs} paired attacks` : ''})`
      : '';
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm ${TONE[meta.tone]}`}
      title={meta.blurb}
    >
      <span className="font-mono text-xs uppercase tracking-wide opacity-70">{badge}</span>
      <span className="font-medium">
        {meta.label}
        {stat}
      </span>
    </span>
  );
}
