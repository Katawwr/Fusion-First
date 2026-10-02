import React from "react";

// The versions and hash behind a card, so a shared copy can be verified.
export default function ProvenanceFooter({ card }) {
  return (
    <div className="mt-3 border-t border-app-border pt-2 font-mono text-[11px] text-app-subtle">
      judge={card.judge_model} · gold={card.gold_version || "n/a"} · crosswalk=
      {card.crosswalk_version} · verify={card.verification_hash}
    </div>
  );
}
