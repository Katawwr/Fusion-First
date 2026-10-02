import React from "react";

const TONE = {
  PROVEN: "var(--ok)",
  PRELIMINARY: "var(--warn)",
  INCONCLUSIVE: "var(--subtle)",
};

// The badge word (PROVEN/PRELIMINARY/INCONCLUSIVE), toned; a PROVEN result adds its p and pair count.
export default function HonestyPill({ badge, p, nPairs }) {
  const tone = TONE[badge] || TONE.INCONCLUSIVE;
  const stat =
    badge === "PROVEN" && typeof p === "number"
      ? ` (p=${p.toFixed(3)}${nPairs ? `, ${nPairs} paired attacks` : ""})`
      : "";
  return (
    <span
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
      {stat && <span style={{ fontWeight: 500 }}>{stat.trim()}</span>}
    </span>
  );
}
