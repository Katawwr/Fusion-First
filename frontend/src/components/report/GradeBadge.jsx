import React from "react";

const TONE = {
  A: "var(--ok)",
  B: "var(--ok)",
  C: "var(--warn)",
  D: "var(--danger)",
  F: "var(--danger)",
};

const SIZES = {
  sm: { box: 32, font: "1rem", radius: "0.6rem" },
  md: { box: 44, font: "1.5rem", radius: "0.75rem" },
  lg: { box: 64, font: "2.25rem", radius: "1rem" },
};

export default function GradeBadge({ grade = "?", size = "md" }) {
  const tone = TONE[grade] || "var(--subtle)";
  const s = SIZES[size] || SIZES.md;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: s.box,
        height: s.box,
        borderRadius: s.radius,
        fontSize: s.font,
        fontWeight: 800,
        lineHeight: 1,
        color: tone,
        background: `color-mix(in srgb, ${tone} 14%, transparent)`,
        border: `1.5px solid ${tone}`,
      }}
    >
      {grade}
    </span>
  );
}
