import React from "react";
import HonestyPill from "./HonestyPill";

// The honesty badge for a before/after result.
export default function HonestyExplainer({ ba }) {
  if (!ba) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.6rem" }}>
      <HonestyPill badge={ba.honesty} p={ba.mcnemar_p} nPairs={ba.n_pairs} />
    </div>
  );
}
