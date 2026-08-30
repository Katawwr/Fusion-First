import React from "react";

// Plain-language text with the real term in a hover/focus tooltip. Educate, don't hide.
// The underline is deliberately faint: these appear many times per report, so a strong
// decoration turns whole paragraphs into what looks like a wall of broken links.
// Usage: <Term term="McNemar's exact test" tip="...">not-luck check</Term>
export default function Term({ children, term, tip, className = "" }) {
  const title = term ? `${term}${tip ? ", " + tip : ""}` : tip;
  return (
    <span
      tabIndex={0}
      title={title}
      className={className}
      style={{
        textDecoration: "underline",
        textDecorationStyle: "dotted",
        textDecorationColor: "var(--border-strong)",
        textUnderlineOffset: "3px",
        cursor: "help",
        outline: "none",
      }}
    >
      {children}
    </span>
  );
}
