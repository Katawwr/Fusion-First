import React from "react";
import { pct } from "../../lib/jargon";

function Stat({ value, label }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div
        style={{
          fontFamily: "'JetBrains Mono', ui-monospace, 'SF Mono', monospace",
          fontSize: "1.125rem",
          fontWeight: 700,
          color: "var(--text)",
          lineHeight: 1.2,
        }}
      >
        {value}
      </div>
      <div
        style={{
          marginTop: "0.15rem",
          fontSize: "0.6875rem",
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--subtle)",
        }}
      >
        {label}
      </div>
    </div>
  );
}

// Bar A: the grader's track record on the known-answer set (a property of the grader, never a
// per-prompt accuracy claim).
export default function JudgeAccuracyBlock({ acc, note }) {
  if (!acc) {
    return (
      <p className="text-sm text-app-muted">
        <strong className="text-app-text">Grader accuracy: </strong>
        {note || "not measured; treat this grade as unverified."}
      </p>
    );
  }
  return (
    <div>
      <p
        style={{
          fontSize: "0.6875rem",
          fontWeight: 600,
          letterSpacing: "0.07em",
          textTransform: "uppercase",
          color: "var(--subtle)",
          marginBottom: "0.5rem",
        }}
      >
        Grader accuracy
      </p>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "1.75rem",
          padding: "0.9rem 1rem",
          borderRadius: "0.85rem",
          background: "var(--surface-2)",
        }}
      >
        <Stat value={pct(acc.recall?.point)} label="recall" />
        <Stat value={pct(acc.precision?.point)} label="precision" />
        <Stat value={acc.cohen_kappa?.toFixed(2)} label="kappa" />
      </div>
      <p
        style={{
          marginTop: "0.6rem",
          fontSize: "0.8125rem",
          color: "var(--subtle)",
          lineHeight: 1.6,
        }}
      >
        {note ? <strong className="text-app-text">{note} </strong> : null}
        {acc.n} known-answer cases{acc.n_unscored ? `, ${acc.n_unscored} unscored` : ""}. Precision:{" "}
        {pct(acc.precision?.low)}–{pct(acc.precision?.high)}, 95% CI.
      </p>
    </div>
  );
}
