import React from "react";
import Term from "../ui/Term";
import { GRADE_LEGEND } from "../../lib/jargon";

// Theme tokens, not raw palette colors, so grades match the rest of the site in both themes.
const TONE = {
  A: "var(--ok)",
  B: "var(--ok)",
  C: "var(--warn)",
  D: "var(--orange)",
  F: "var(--danger)",
};

const SIZES = {
  sm: { box: 32, font: "1rem", radius: "0.6rem" },
  md: { box: 44, font: "1.5rem", radius: "0.75rem" },
  lg: { box: 64, font: "2.25rem", radius: "1rem" },
};

// The A-F grade (safety or quality). Legend (real thresholds) lives in the tooltip.
export default function GradeBadge({ grade = "?", size = "md" }) {
  const tone = TONE[grade] || "var(--subtle)";
  const s = SIZES[size] || SIZES.md;
  return (
    <Term term="Grade" tip={GRADE_LEGEND}>
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
    </Term>
  );
}
