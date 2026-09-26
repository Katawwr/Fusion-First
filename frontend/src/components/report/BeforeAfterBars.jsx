import React from "react";
import Term from "../ui/Term";
import HonestyExplainer from "./HonestyExplainer";
import { BOOTSTRAP_TIP, pct, STATS } from "../../lib/jargon";

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

// The screenshot moment: red baseline bar over green hardened bar, with the honest delta + badge.
export default function BeforeAfterBars({ ba }) {
  if (!ba) return null;
  const red = ba.absolute_reduction || {};
  return (
    <div className="flex flex-col gap-3">
      <Bar label="Before" rate={ba.baseline_issue_rate} tone="var(--danger)" />
      <Bar label="After" rate={ba.hardened_issue_rate} tone="var(--ok)" />
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <p className="text-sm text-app-muted">
          <strong>−{pct(red.point)}</strong> of{" "}
          <Term term="issue rate" tip={STATS.issue_rate.tip}>
            attacks now get through
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
