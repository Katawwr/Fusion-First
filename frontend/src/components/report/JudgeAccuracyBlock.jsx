import React from 'react';
import Term from '../ui/Term';
import { pct, STATS } from '../../lib/jargon';

// "How much can you trust this grade?" — Bar A, framed as the examiner's track record on our
// known-answer set (a property of the judge, never a per-user-prompt accuracy claim).
export default function JudgeAccuracyBlock({ acc }) {
  if (!acc) {
    return (
      <p className="text-sm text-app-muted">
        Examiner calibration runs in the Prove tier — this scan reports the before/after result on
        your own prompt.
      </p>
    );
  }
  return (
    <div className="space-y-1 text-sm text-app-muted">
      <p className="font-medium text-app-text">How much can you trust this grade?</p>
      <p>
        We double-checked the{' '}
        <Term term="LLM-as-judge" tip={STATS.judge.tip}>
          AI examiner
        </Term>{' '}
        against {acc.n} known-answer cases: it{' '}
        <Term term="recall" tip={STATS.recall.tip}>
          caught {pct(acc.recall?.point)} of real issues
        </Term>{' '}
        and was{' '}
        <Term term="precision" tip={STATS.precision.tip}>
          right {pct(acc.precision?.point)} of the time when it raised a flag
        </Term>
        .
      </p>
      <p className="text-app-muted">
        <Term term="Wilson 95% CI" tip={STATS.wilson_ci.tip}>
          We're confident the true precision is between {pct(acc.precision?.low)} and{' '}
          {pct(acc.precision?.high)}.
        </Term>{' '}
        <Term term="Cohen's kappa" tip={STATS.kappa.tip}>
          Agreement beyond luck: {acc.cohen_kappa?.toFixed(2)}.
        </Term>
      </p>
    </div>
  );
}
