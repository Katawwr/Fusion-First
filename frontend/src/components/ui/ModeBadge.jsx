import React from 'react';

// Small DEMO / REAL chip so history and headers never mix modes silently.
export default function ModeBadge({ demonstration }) {
  return demonstration ? (
    <span className="rounded-full border border-warn/45 bg-warn/12 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-warn">
      Demo
    </span>
  ) : (
    <span className="rounded-full border border-ok/45 bg-ok/12 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-ok">
      Real
    </span>
  );
}
