import React, { useState } from "react";
import Card from "../ui/Card";
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
        {quality ? "Defects" : "What got through"}
      </p>
      <ul className="flex flex-col gap-1">
        {shown.map((o) => (
          <li
            key={o.probe_id}
            className="flex items-start gap-2 text-sm text-app-muted"
          >
            <span
              aria-hidden
              style={{
                flexShrink: 0,
                width: 6,
                height: 6,
                marginTop: "0.5rem",
                borderRadius: "50%",
                background: "var(--subtle)",
              }}
            />
            <span>{o.attack_label}</span>
          </li>
        ))}
      </ul>
      {gotThrough.length > 3 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="self-start text-xs text-accent-ink hover:underline"
        >
          {open ? "Show fewer" : `Show all ${gotThrough.length}`}
        </button>
      )}
    </div>
  );
}

// One check's card: grade, title, OWASP codes, what got through, trust block, grader accuracy, then the
// optional prompt fix's before/after. No scenario line: the setup step already showed it.
export default function ReportCard({ card, outcomes = [] }) {
  const meta = metaFor(card.check);
  const quality = card.kind === "quality" || isQualityCheck(card.check);
  return (
    <Card variant="elevated" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <GradeBadge grade={card.grade} size="md" />
        <h3 className="text-base font-semibold text-app-text">{meta.label}</h3>
        {(card.owasp_tags || []).map((t, i) => (
          <OwaspChip key={i} tag={t} />
        ))}
      </div>

      <AttackList outcomes={outcomes} quality={quality} />
      <TrustStrip card={card} />
      <JudgeAccuracyBlock
        acc={card.judge_accuracy}
        note={card.judge_accuracy_note}
        source={card.trust?.judge_accuracy_source}
      />
      {/* The measurement comes first; the optional prompt fix's paired result follows it. */}
      {card.before_after && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-app-text">Prompt fix (optional)</p>
          <BeforeAfterBars
            ba={card.before_after}
            quality={quality}
          />
        </div>
      )}
      <ProvenanceFooter card={card} />
    </Card>
  );
}
