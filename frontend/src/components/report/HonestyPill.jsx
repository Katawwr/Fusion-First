import React from "react";
import { HONESTY } from "../../lib/jargon";

const TONE = {
  good: "var(--ok)",
  warn: "var(--warn)",
  bad: "var(--subtle)",
};

// The differentiator: translated but never softened. Keeps the real badge word (PROVEN/…)
// visible as a small caps prefix, with the plain-language reading beside it.
export default function HonestyPill({ badge, p, nPairs }) {
  const meta = HONESTY[badge] || HONESTY.INCONCLUSIVE;
  const tone = TONE[meta.tone] || TONE.bad;
  const stat =
    badge === "PROVEN" && typeof p === "number"
      ? ` (p=${p.toFixed(3)}${nPairs ? `, ${nPairs} paired attacks` : ""})`
      : "";
  return (
    <span
      title={meta.blurb}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.5rem",
        borderRadius: 9999,
        padding: "0.3rem 0.75rem",
        fontSize: "0.8125rem",
        color: tone,
        background: `color-mix(in srgb, ${tone} 12%, transparent)`,
      }}
    >
      <span
        style={{
          fontSize: "0.625rem",
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          opacity: 0.85,
        }}
      >
        {badge}
      </span>
      <span style={{ fontWeight: 500 }}>
        {meta.label}
        {stat}
      </span>
    </span>
  );
}
