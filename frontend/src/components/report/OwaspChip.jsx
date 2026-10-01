import React from "react";

// OWASP crosswalk reference: LLM01 / ASI01. Signals rigor without demanding the reader know the
// codes, so it is set as a quiet micro-label rather than a boxed chip that competes with the title.
export default function OwaspChip({ tag }) {
  const codes = [tag?.llm, tag?.asi].filter(Boolean).join(" · ");
  if (!codes) return null;
  return (
    <span
      style={{
        fontSize: "0.6875rem",
        fontWeight: 600,
        letterSpacing: "0.07em",
        textTransform: "uppercase",
        color: "var(--subtle)",
        whiteSpace: "nowrap",
      }}
      title="Mapped to the OWASP Top 10 for LLM apps (2025) and Agentic AI (2026); the ASI (Agentic) codes are provisional."
    >
      {codes}
    </span>
  );
}
