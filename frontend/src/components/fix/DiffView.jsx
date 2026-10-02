import React from "react";

// Harden only appends, so the diff is the original (dim) plus the added block (highlighted).
export default function DiffView({ original, guardBlock }) {
  return (
    <div
      style={{
        overflow: "hidden",
        borderRadius: "0.85rem",
        border: "1px solid var(--border)",
        background: "var(--surface-2)",
      }}
    >
      <pre
        style={{
          maxHeight: "24rem",
          overflow: "auto",
          padding: "0.9rem 1rem",
          margin: 0,
          fontSize: "0.8125rem",
          lineHeight: 1.7,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        <code style={{ color: "var(--subtle)" }}>
          {original.replace(/\n+$/, "")}
        </code>
        {"\n\n"}
        <code
          style={{
            display: "block",
            borderRadius: "0.5rem",
            padding: "0.5rem 0.6rem",
            background: "var(--accent-soft)",
            color: "var(--text)",
          }}
        >
          {guardBlock.split("\n").map((line, i) => (
            <span key={i} style={{ display: "block" }}>
              <span
                style={{
                  userSelect: "none",
                  color: "var(--accent-ink)",
                  fontWeight: 700,
                }}
              >
                +{" "}
              </span>
              {line}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}
