import React from "react";
import { isQualityCheck, metaFor } from "../../lib/jargon";

// One graded item on the prompt as written. Only a failure takes a status colour.
export default function AttackFeedRow({ outcome }) {
  const fooled = outcome.baseline_issue;
  const tone = fooled ? "var(--danger)" : "var(--subtle)";
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "0.75rem",
        padding: "0.7rem 0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <span
        style={{
          flex: 1,
          minWidth: 0,
          fontSize: "0.9375rem",
          color: "var(--muted)",
          lineHeight: 1.55,
        }}
      >
        <span style={{ display: "block", fontSize: "0.75rem", color: "var(--subtle)" }}>
          {metaFor(outcome.check).label}
        </span>
        {outcome.attack_label}
      </span>
      <span
        style={{
          flexShrink: 0,
          borderRadius: 9999,
          padding: "0.15rem 0.6rem",
          fontSize: "0.75rem",
          fontWeight: 600,
          color: tone,
          background: `color-mix(in srgb, ${tone} 14%, transparent)`,
          whiteSpace: "nowrap",
        }}
      >
        {isQualityCheck(outcome.check) ? (fooled ? "Defect" : "OK") : fooled ? "Got through" : "Resisted"}
      </span>
    </div>
  );
}
