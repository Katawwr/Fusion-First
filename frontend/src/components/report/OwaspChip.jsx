import React from 'react';

// OWASP crosswalk chip: LLM01 / ASI01. Signals rigor without demanding the reader know the codes.
export default function OwaspChip({ tag }) {
  const codes = [tag?.llm, tag?.asi].filter(Boolean).join(' · ');
  if (!codes) return null;
  return (
    <span
      className="rounded-md border border-fusion-cyan-medium bg-fusion-cyan-light px-2 py-0.5 font-mono text-xs text-fusion-cyan"
      title="Mapped to the OWASP Top 10 for LLM apps (2025) and Agentic AI (2026)."
    >
      {codes}
    </span>
  );
}
