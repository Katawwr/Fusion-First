import React from "react";
import { INDEPENDENCE } from "../../lib/jargon";
import { scoredSentence } from "../../lib/trust";

function Row({ label, children }) {
  return (
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "baseline" }}>
      <span
        style={{
          fontSize: "0.6875rem",
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--subtle)",
          minWidth: "7.5rem",
        }}
      >
        {label}
      </span>
      <span style={{ fontSize: "0.875rem", color: "var(--text)" }}>{children}</span>
    </div>
  );
}

export default function TrustStrip({ card }) {
  const t = card?.trust;
  if (!t) return null;
  const canned = t.execution === "canned";
  const scored = scoredSentence(t);
  return (
    <div
      data-testid="trust-strip"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.35rem",
        padding: "0.8rem 1rem",
        borderRadius: "0.85rem",
        border: "1px solid var(--border)",
        background: "var(--surface-2)",
      }}
    >
      <Row label="What ran">
        {canned
          ? "Recorded responses"
          : "Your prompt, live on the target model"}
      </Row>
      <Row label="Grader">
        {canned ? "Offline stand-in grader" : t.judge_id || "unknown"}
        {!canned && t.judge_backend ? ` via ${t.judge_backend}` : ""}
      </Row>
      {!canned && t.independence && (
        <Row label="Independence">
          <span title={t.independence_disclosure || ""}>
            {INDEPENDENCE[t.independence] || t.independence}
          </span>
        </Row>
      )}
      {scored && <Row label="Coverage">{scored}</Row>}
      {t.sampling_pinned === false && (
        <Row label="Repeatability">
          Sampling not pinned; repeat runs may differ.
        </Row>
      )}
    </div>
  );
}
