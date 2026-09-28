import React from "react";
import Term from "../ui/Term";

// Small monospace provenance line, costs nothing, signals rigor, makes a shared card verifiable.
export default function ProvenanceFooter({ card }) {
  return (
    <div className="mt-3 border-t border-app-border pt-2 font-mono text-[11px] text-app-subtle">
      <Term
        term="Verification hash"
        tip="Hash of the data and versions behind this card, for verifying a shared copy."
      >
        judge={card.judge_model} · gold={card.gold_version || "n/a"} ·
        crosswalk=
        {card.crosswalk_version} · verify={card.verification_hash}
      </Term>
    </div>
  );
}
