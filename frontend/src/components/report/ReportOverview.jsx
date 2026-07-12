import React from 'react';
import GradeBadge from './GradeBadge';
import DemoBanner from '../ui/DemoBanner';
import { pct } from '../../lib/jargon';

// One plain sentence + the overall grade. Worst per-check baseline rate drives the headline number.
export default function ReportOverview({ result }) {
  const worstBaseline = Math.max(
    0,
    ...result.cards.map((c) => c.before_after?.baseline_issue_rate || 0)
  );
  return (
    <div className="space-y-4">
      {result.demonstration && <DemoBanner />}
      <div className="flex items-center gap-5">
        <GradeBadge grade={result.overall_grade} size="lg" />
        <div>
          <h2 className="text-2xl font-bold text-app-text">
            Grade {result.overall_grade} — {result.target_name}
          </h2>
          <p className="mt-1 text-app-muted">
            At baseline, attacks fooled your bot in up to{' '}
            <strong className="text-app-text">{pct(worstBaseline)}</strong> of attempts. Hardening moves
            the needle — see each test below.
          </p>
        </div>
      </div>
    </div>
  );
}
