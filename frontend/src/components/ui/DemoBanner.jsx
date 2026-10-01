import React from "react";
import { Info } from "lucide-react";

// Non-dismissable ribbon shown wherever a card carries demonstration=true (the schema flag drives
// it, never inferred client-side). Neutral, not a status colour: the demo is not a result.
export default function DemoBanner({ className = "" }) {
  return (
    <div
      className={className}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "0.6rem",
        padding: "0.75rem 1rem",
        borderRadius: "0.85rem",
        border: "1px solid var(--border-strong)",
        background: "var(--surface-2)",
        fontSize: "0.9375rem",
        lineHeight: 1.6,
        color: "var(--muted)",
      }}
    >
      <Info size={17} style={{ flexShrink: 0, marginTop: "0.2rem" }} aria-hidden />
      <span>
        <strong style={{ color: "var(--text)" }}>Demo:</strong> recorded responses, scored by an offline
        stand-in grader. Not a result for your agent.
      </span>
    </div>
  );
}
