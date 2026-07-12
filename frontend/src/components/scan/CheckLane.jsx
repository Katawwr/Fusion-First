import React from 'react';
import GradeBadge from '../report/GradeBadge';
import { checkMeta } from '../../lib/jargon';

// One lane per enabled check. Progressive completion is the dopamine loop: spinner → live tally →
// grade flip when this check's card arrives.
export default function CheckLane({ check, run = 0, issues = 0, grade = null }) {
  const meta = checkMeta(check);
  const done = grade != null;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-app-border bg-app-elev p-3">
      <span className="text-xl" aria-hidden>
        {meta.icon}
      </span>
      <div className="flex-1">
        <p className="text-sm font-medium text-app-text">{meta.label}</p>
        <p className="text-xs text-app-muted">
          {done
            ? `${run} attacks run · ${issues} got through`
            : run
              ? `${run} attacks run · ${issues} got through`
              : 'waiting…'}
        </p>
      </div>
      {done ? (
        <GradeBadge grade={grade} size="sm" />
      ) : (
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-fusion-cyan border-t-transparent" />
      )}
    </div>
  );
}
