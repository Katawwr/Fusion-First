import React from 'react';

// Non-dismissable honesty ribbon shown wherever a card carries demonstration=true.
// The schema flag drives it — never inferred client-side.
export default function DemoBanner({ className = '' }) {
  return (
    <div
      className={`flex items-center gap-2 rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-warn ${className}`}
    >
      <span aria-hidden>⚠️</span>
      <span>
        <strong>Demo scan</strong> — an offline stand-in examiner on recorded runs. This shows how
        Fusion works; it is <em>not</em> a claim about your bot. Run a real scan for that.
      </span>
    </div>
  );
}
