import React from "react";

// OWASP crosswalk codes (LLM01 · ASI01) as a quiet micro-label.
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
