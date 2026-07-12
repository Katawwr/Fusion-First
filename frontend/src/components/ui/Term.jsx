import React from 'react';

// Plain-language text with the real term in a hover/focus tooltip. Educate, don't hide.
// Usage: <Term term="McNemar's exact test" tip="...">not-luck check</Term>
export default function Term({ children, term, tip, className = '' }) {
  const title = term ? `${term}${tip ? ' — ' + tip : ''}` : tip;
  return (
    <span
      tabIndex={0}
      title={title}
      className={`underline decoration-dotted decoration-fusion-cyan/60 underline-offset-2 cursor-help outline-none focus:decoration-fusion-cyan ${className}`}
    >
      {children}
    </span>
  );
}
