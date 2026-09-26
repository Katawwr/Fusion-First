import React from "react";
import Term from "../ui/Term";
import HonestyExplainer from "./HonestyExplainer";
import { BOOTSTRAP_TIP, pct, STATS } from "../../lib/jargon";
import { deltaSentence } from "../../lib/trust";

function Bar({ label, rate, tone }) {
  const width = Math.max(2, Math.round((rate || 0) * 100));
  // The value always sits OUTSIDE the fill, in a fixed-width column, so Before and After
  // read down a straight edge instead of jumping in and out of the bar with the value.
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
      <span
        style={{
          width: "3.75rem",
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
          color: tone,
        }}
      >
        {pct(rate)}
      </span>
    </div>
  );
}

// The screenshot moment: the prompt as written over the fixed prompt, with the honest delta + badge.
// Safety: issue = an attack got through. Quality: issue = an answer with a defect (fix cost).
export default function BeforeAfterBars({ ba, quality = false }) {
  if (!ba) return null;
  const red = ba.absolute_reduction || {};
  return (
    <div className="flex flex-col gap-3">
      <Bar
        label={quality ? "As written" : "Before"}
        rate={ba.baseline_issue_rate}
        tone={quality ? "var(--accent)" : "var(--danger)"}
      />
      <Bar
        label={quality ? "With fix" : "After"}
        rate={ba.hardened_issue_rate}
        tone={
          quality
            ? ba.hardened_issue_rate > ba.baseline_issue_rate
              ? "var(--warn)"
              : "var(--accent)"
            : "var(--ok)"
        }
      />
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <p className="text-sm text-app-muted">
          <Term term="issue rate" tip={STATS.issue_rate.tip}>
            <strong>{deltaSentence(red.point, quality)}</strong>
          </Term>{" "}
          <Term term="95% bootstrap range" tip={BOOTSTRAP_TIP} className="text-app-muted">
            (95% range {pct(red.low)} to {pct(red.high)})
          </Term>
        </p>
      </div>
      <HonestyExplainer ba={ba} />
    </div>
  );
}
