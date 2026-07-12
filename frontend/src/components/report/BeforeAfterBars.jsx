import React from 'react';
import Term from '../ui/Term';
import HonestyPill from './HonestyPill';
import { pct, STATS } from '../../lib/jargon';

function Bar({ label, rate, tone }) {
  const width = Math.max(2, Math.round((rate || 0) * 100));
  return (
    <div className="flex items-center gap-3">
      <span className="w-20 shrink-0 text-sm text-app-muted">{label}</span>
      <div className="h-6 flex-1 overflow-hidden rounded bg-black/20">
        <div
          className={`flex h-full items-center justify-end rounded pr-2 text-xs font-semibold text-white ${tone}`}
          style={{ width: `${width}%` }}
        >
          {pct(rate)}
        </div>
      </div>
    </div>
  );
}

// The screenshot moment: red baseline bar over green hardened bar, with the honest delta + badge.
export default function BeforeAfterBars({ ba }) {
  if (!ba) return null;
  const red = ba.absolute_reduction || {};
  return (
    <div className="space-y-3">
      <Bar label="Before" rate={ba.baseline_issue_rate} tone="bg-red-500" />
      <Bar label="After" rate={ba.hardened_issue_rate} tone="bg-emerald-500" />
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <p className="text-sm text-app-muted">
          <strong>−{pct(red.point)}</strong> of{' '}
          <Term term="issue rate" tip={STATS.issue_rate.tip}>
            attacks now get through
          </Term>{' '}
          <Term term="Wilson 95% CI" tip={STATS.wilson_ci.tip} className="text-app-muted">
            (range {pct(red.low)}–{pct(red.high)})
          </Term>
        </p>
        <HonestyPill badge={ba.honesty} p={ba.mcnemar_p} nPairs={ba.n_pairs} />
      </div>
    </div>
  );
}
