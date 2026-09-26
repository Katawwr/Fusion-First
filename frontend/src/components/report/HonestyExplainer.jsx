import React from "react";
import HonestyPill from "./HonestyPill";
import { HONESTY } from "../../lib/jargon";

// The honesty badge plus what it means, inline (not hidden in a tooltip), and — when the result
// is not PROVEN — the server's plain-language reasons why ("needs at least 20 paired attacks…").
export default function HonestyExplainer({ ba }) {
  if (!ba) return null;
  const meta = HONESTY[ba.honesty] || HONESTY.INCONCLUSIVE;
  const reasons = ba.honesty_reasons || [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.6rem" }}>
        <HonestyPill badge={ba.honesty} p={ba.mcnemar_p} nPairs={ba.n_pairs} />
        <span style={{ fontSize: "0.8125rem", color: "var(--muted)" }}>{meta.blurb}</span>
      </div>
      {ba.honesty !== "PROVEN" && reasons.length > 0 && (
        <details style={{ fontSize: "0.8125rem", color: "var(--muted)" }}>
          <summary style={{ cursor: "pointer" }}>Why not PROVEN?</summary>
          <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.2rem", listStyle: "disc" }}>
            {reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
