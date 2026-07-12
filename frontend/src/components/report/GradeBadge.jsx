import React from 'react';
import Term from '../ui/Term';
import { GRADE_LEGEND } from '../../lib/jargon';

const TONE = {
  A: 'from-emerald-400 to-emerald-600 text-white',
  B: 'from-emerald-400 to-emerald-600 text-white',
  C: 'from-amber-400 to-amber-500 text-fusion-purple',
  D: 'from-orange-500 to-red-500 text-white',
  F: 'from-red-500 to-red-700 text-white',
};

const SIZES = {
  sm: 'h-10 w-10 text-xl',
  md: 'h-16 w-16 text-4xl',
  lg: 'h-24 w-24 text-6xl',
};

// The A–F safety grade. Legend (real thresholds) lives in the tooltip.
export default function GradeBadge({ grade = '?', size = 'md' }) {
  const tone = TONE[grade] || 'from-gray-400 to-gray-600 text-white';
  return (
    <Term term="Safety grade" tip={GRADE_LEGEND}>
      <span
        className={`inline-flex items-center justify-center rounded-2xl bg-gradient-to-br font-bold shadow-lg ${tone} ${SIZES[size]}`}
      >
        {grade}
      </span>
    </Term>
  );
}
