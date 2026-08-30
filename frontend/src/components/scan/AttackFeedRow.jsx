import React from "react";
import CheckIcon from "../ui/CheckIcon";

// Newest-first stream of judged attacks: "Resisted" or "Fooled" on the baseline arm
// (the raw prompt under attack).
export default function AttackFeedRow({ outcome }) {
  const fooled = outcome.baseline_issue;
  const tone = fooled ? "var(--danger)" : "var(--ok)";
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
      <span style={{ marginTop: "0.1rem", flexShrink: 0 }}>
        <CheckIcon check={outcome.check} size={26} />
      </span>
      <span
        style={{
          flex: 1,
          minWidth: 0,
          fontSize: "0.9375rem",
          color: "var(--muted)",
          lineHeight: 1.55,
        }}
      >
        {outcome.attack_label}
      </span>
      {/* Soft tinted pill, not an outline: these repeat down a long feed, and a column of
          hard-bordered chips reads as noise. */}
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
        {fooled ? "Fooled" : "Resisted"}
      </span>
    </div>
  );
}
