import React from "react";
import Term from "../ui/Term";
import { pct, STATS } from "../../lib/jargon";

function Stat({ value, label, term, tip }) {
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
        <Term term={term} tip={tip}>
          {label}
        </Term>
      </div>
    </div>
  );
}

// "How much can you trust this grade?", Bar A, framed as the examiner's track record on our
// known-answer set (a property of the judge, never a per-user-prompt accuracy claim).
// Presented as a compact stat row: the numbers are the point, so they read at a glance
// instead of being buried in a paragraph of underlined phrases.
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
        <Stat
          value={pct(acc.recall?.point)}
          label="recall"
          term="recall"
          tip={STATS.recall.tip}
        />
        <Stat
          value={pct(acc.precision?.point)}
          label="precision"
          term="precision"
          tip={STATS.precision.tip}
        />
        <Stat
          value={acc.cohen_kappa?.toFixed(2)}
          label="kappa"
          term="Cohen's kappa"
          tip={STATS.kappa.tip}
        />
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
