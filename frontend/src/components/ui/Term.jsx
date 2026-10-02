import React from "react";

// Plain text. `term` and `tip` are kept on call sites as documentation of the underlying statistic,
// but nothing is shown on hover (owner 2026-10-02: no underlines or tooltips in the report card).
// Usage: <Term term="McNemar's exact test" tip="...">not-luck check</Term>
// eslint-disable-next-line no-unused-vars
export default function Term({ children, term, tip, className = "" }) {
  return <span className={className || undefined}>{children}</span>;
}
