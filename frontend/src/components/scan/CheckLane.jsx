import React from "react";
import GradeBadge from "../report/GradeBadge";
import { isQualityCheck, metaFor } from "../../lib/jargon";

// One lane per enabled check: spinner, live tally, then the grade when this check's card arrives.
export default function CheckLane({
  check,
  run = 0,
  issues = 0,
  grade = null,
}) {
  const meta = metaFor(check);
  const done = grade != null;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.875rem",
        padding: "1rem",
        borderRadius: "1.1rem",
        border: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontWeight: 600, color: "var(--text)", margin: 0 }}>
          {meta.label}
        </p>
        <p
          style={{
            margin: "0.15rem 0 0",
            fontSize: "0.875rem",
            color: "var(--muted)",
          }}
        >
          {run
            ? isQualityCheck(check)
              ? `${run} requests run, ${issues} with a defect`
              : `${run} attacks run, ${issues} got through`
            : "no results yet"}
        </p>
      </div>
      {done ? (
        <GradeBadge grade={grade} size="sm" />
      ) : (
        <span
          aria-hidden
          className="animate-spin"
          style={{
            width: 20,
            height: 20,
            flexShrink: 0,
            borderRadius: "50%",
            border: "2px solid var(--accent)",
            borderTopColor: "transparent",
          }}
        />
      )}
    </div>
  );
}
