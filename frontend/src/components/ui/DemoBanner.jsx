import React from "react";
import { AlertTriangle } from "lucide-react";

// Non-dismissable honesty ribbon shown wherever a card carries demonstration=true.
// The schema flag drives it, never inferred client-side.
export default function DemoBanner({ className = "" }) {
  return (
    <div
      className={className}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "0.65rem",
        padding: "0.85rem 1rem",
        borderRadius: "0.85rem",
        border: "1px solid color-mix(in srgb, var(--warn) 40%, transparent)",
        background: "color-mix(in srgb, var(--warn) 10%, transparent)",
        fontSize: "0.9375rem",
        lineHeight: 1.6,
        color: "var(--warn)",
      }}
    >
      <AlertTriangle
        size={18}
        style={{ flexShrink: 0, marginTop: "0.15rem" }}
        aria-hidden
      />
      <span>
        <strong>Demo scan:</strong> recorded runs, scored by an offline stand-in
        grader. It is <em>not</em> a result for your agent.
      </span>
    </div>
  );
}
