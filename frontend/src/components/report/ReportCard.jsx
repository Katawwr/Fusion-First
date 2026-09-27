import React, { useState } from "react";
import { Check, X } from "lucide-react";
import Card from "../ui/Card";
import CheckIcon from "../ui/CheckIcon";
import GradeBadge from "./GradeBadge";
import OwaspChip from "./OwaspChip";
import BeforeAfterBars from "./BeforeAfterBars";
import JudgeAccuracyBlock from "./JudgeAccuracyBlock";
import ProvenanceFooter from "./ProvenanceFooter";
import TrustStrip from "./TrustStrip";
import { isQualityCheck, metaFor } from "../../lib/jargon";

function AttackList({ outcomes, quality = false }) {
  const [open, setOpen] = useState(false);
  const gotThrough = outcomes.filter((o) => o.baseline_issue === true);
  if (!gotThrough.length) return null;
  const shown = open ? gotThrough : gotThrough.slice(0, 3);
  return (
    <div className="flex flex-col gap-1">
      <p className="text-sm font-medium text-app-text">
        {quality ? "What it got wrong" : "What got through"}
      </p>
      <ul className="flex flex-col gap-1">
        {shown.map((o) => (
          <li
            key={o.probe_id}
            className="flex items-start gap-2 text-sm text-app-muted"
          >
            {/* The marker alone carries it: green check = the fix closes this, red X = still open. */}
            {o.hardened_issue ? (
              <X
                size={15}
                color="var(--danger)"
                style={{ flexShrink: 0, marginTop: "0.2rem" }}
                aria-label={quality ? "still wrong with the fixed prompt" : "still open after the fix"}
              />
            ) : (
              <Check
                size={15}
                color="var(--ok)"
                style={{ flexShrink: 0, marginTop: "0.2rem" }}
                aria-label={quality ? "right with the fixed prompt" : "closed by the fix"}
              />
            )}
            <span>{o.attack_label}</span>
          </li>
        ))}
      </ul>
      {gotThrough.length > 3 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-xs text-fusion-cyan hover:underline"
        >
          {open ? "Show fewer" : `Show all ${gotThrough.length}`}
        </button>
      )}
    </div>
  );
}

// One check's card: grade, plain title, OWASP chips, what-got-through, before/after, trust block.
export default function ReportCard({ card, outcomes = [] }) {
  const meta = metaFor(card.check);
  const quality = card.kind === "quality" || isQualityCheck(card.check);
  return (
    <Card variant="elevated" className="flex flex-col gap-4">
      {/* The scenario line is dropped here: the reader chose these tests by that description on
          the setup step, so repeating it on every card is noise. */}
      <div className="flex items-center gap-3">
        <GradeBadge grade={card.grade} size="md" />
        <CheckIcon check={card.check} size={28} />
        <h3 className="text-base font-semibold text-app-text">{meta.label}</h3>
        {(card.owasp_tags || []).map((t, i) => (
          <OwaspChip key={i} tag={t} />
        ))}
      </div>

      <AttackList outcomes={outcomes} quality={quality} />
      <BeforeAfterBars
        ba={card.before_after}
        quality={quality}
        canned={card.trust?.execution === "canned"}
      />
      <TrustStrip card={card} />
      <JudgeAccuracyBlock
        acc={card.judge_accuracy}
        note={card.judge_accuracy_note}
        source={card.trust?.judge_accuracy_source}
      />
      <ProvenanceFooter card={card} />
    </Card>
  );
}
