import React, { useState } from 'react';
import Card from '../ui/Card';
import GradeBadge from './GradeBadge';
import OwaspChip from './OwaspChip';
import BeforeAfterBars from './BeforeAfterBars';
import JudgeAccuracyBlock from './JudgeAccuracyBlock';
import ProvenanceFooter from './ProvenanceFooter';
import { checkMeta } from '../../lib/jargon';

function AttackList({ outcomes }) {
  const [open, setOpen] = useState(false);
  const gotThrough = outcomes.filter((o) => o.baseline_issue);
  if (!gotThrough.length) return null;
  const shown = open ? gotThrough : gotThrough.slice(0, 3);
  return (
    <div className="space-y-1">
      <p className="text-sm font-medium text-app-text">What got through</p>
      <ul className="space-y-1">
        {shown.map((o) => (
          <li key={o.probe_id} className="flex items-start gap-2 text-sm text-app-muted">
            <span className={o.hardened_issue ? 'text-red-400' : 'text-emerald-400'} aria-hidden>
              {o.hardened_issue ? '✗' : '✓'}
            </span>
            <span>{o.attack_label}</span>
          </li>
        ))}
      </ul>
      {gotThrough.length > 3 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-xs text-fusion-cyan hover:underline"
        >
          {open ? 'Show fewer' : `Show all ${gotThrough.length}`}
        </button>
      )}
    </div>
  );
}

// One check's card: grade, plain title, OWASP chips, what-got-through, before/after, trust block.
export default function ReportCard({ card, outcomes = [] }) {
  const meta = checkMeta(card.check);
  return (
    <Card variant="elevated" className="space-y-4">
      <div className="flex items-start gap-4">
        <GradeBadge grade={card.grade} size="md" />
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-2xl" aria-hidden>
              {meta.icon}
            </span>
            <h3 className="text-lg font-semibold text-app-text">{meta.label}</h3>
            {(card.owasp_tags || []).map((t, i) => (
              <OwaspChip key={i} tag={t} />
            ))}
          </div>
          <p className="mt-1 text-sm text-app-muted">{meta.scenario}</p>
        </div>
      </div>

      <AttackList outcomes={outcomes} />
      <BeforeAfterBars ba={card.before_after} />
      <JudgeAccuracyBlock acc={card.judge_accuracy} />
      <ProvenanceFooter card={card} />
    </Card>
  );
}
