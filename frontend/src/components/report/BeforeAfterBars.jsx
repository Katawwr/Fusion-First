import React from "react";
import HonestyPill from "./HonestyPill";
import { pct } from "../../lib/jargon";
import { deltaSentence } from "../../lib/trust";

function Bar({ label, rate, tone, ink = "var(--muted)" }) {
  const width = Math.max(2, Math.round((rate || 0) * 100));
  // The value sits outside the fill in a fixed-width column so both rows read down a straight edge.
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
      <span
        style={{
          width: "5.25rem",
          flexShrink: 0,
          fontSize: "0.875rem",
          fontWeight: 500,
          color: "var(--muted)",
        }}
      >
        {label}
      </span>
      <div
        style={{
          height: "0.85rem",
          flex: 1,
          minWidth: 0,
          overflow: "hidden",
          borderRadius: "9999px",
          background: "var(--surface-2)",
        }}
      >
        <div
          style={{
            height: "100%",
            borderRadius: "9999px",
            background: tone,
            width: `${width}%`,
            transition: "width .4s ease",
          }}
        />
      </div>
      <span
        style={{
          width: "3rem",
          flexShrink: 0,
          textAlign: "right",
          fontFamily: "'JetBrains Mono', ui-monospace, 'SF Mono', monospace",
          fontSize: "0.8125rem",
          fontWeight: 700,
          color: ink,
        }}
      >
        {pct(rate)}
      </span>
    </div>
  );
}

// The prompt as written (grey) over the fixed prompt (purple, or pink when the fix adds issues).
// Safety: issue = an attack got through. Quality: issue = an answer with a defect.
export default function BeforeAfterBars({ ba, quality = false, showBadge = true }) {
  if (!ba) return null;
  const red = ba.absolute_reduction || {};
  const costs = ba.hardened_issue_rate > ba.baseline_issue_rate;
  return (
    <div className="flex flex-col gap-3">
      <Bar
        label="As written"
        rate={ba.baseline_issue_rate}
        tone="var(--chart-grey)"
      />
      <Bar
        label="With fix"
        rate={ba.hardened_issue_rate}
        tone={costs ? "var(--pink)" : "var(--accent)"}
        ink={costs ? "var(--pink-ink)" : "var(--accent-ink)"}
      />
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <p className="text-sm text-app-muted">
          <strong>{deltaSentence(red.point, quality)}</strong> (95% range {pct(red.low)} to {pct(red.high)})
        </p>
      </div>
      {showBadge && (
        <div>
          <HonestyPill badge={ba.honesty} p={ba.mcnemar_p} nPairs={ba.n_pairs} />
        </div>
      )}
    </div>
  );
}
