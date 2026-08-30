import React from "react";
import { Check } from "lucide-react";
import CheckIcon from "../ui/CheckIcon";
import { checkMeta } from "../../lib/jargon";

// A test framed as a plain question. Selection is quiet: a hairline accent border and a small
// filled check, never a saturated slab, so four selected cards do not shout over the page.
export default function CheckToggleCard({ check, enabled, onToggle }) {
  const meta = checkMeta(check);
  return (
    <button
      type="button"
      onClick={() => onToggle(check)}
      aria-pressed={enabled}
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto",
        gap: "0.875rem",
        alignItems: "start",
        width: "100%",
        height: "100%",
        padding: "1.15rem",
        textAlign: "left",
        borderRadius: "1rem",
        border: `1px solid ${enabled ? "var(--accent)" : "var(--border)"}`,
        background: "var(--surface)",
        boxShadow: enabled ? "var(--shadow-sm)" : "none",
        opacity: enabled ? 1 : 0.62,
        cursor: "pointer",
        transition: "border-color .18s ease, opacity .18s ease, box-shadow .18s ease",
      }}
      onMouseEnter={(e) => {
        if (!enabled) e.currentTarget.style.opacity = "0.85";
      }}
      onMouseLeave={(e) => {
        if (!enabled) e.currentTarget.style.opacity = "0.62";
      }}
    >
      <CheckIcon check={check} size={36} />

      <span style={{ minWidth: 0 }}>
        <span
          style={{
            display: "block",
            fontSize: "0.9375rem",
            fontWeight: 600,
            color: "var(--text)",
            lineHeight: 1.35,
          }}
        >
          {meta.label}
        </span>
        <span
          style={{
            display: "block",
            marginTop: "0.2rem",
            fontSize: "0.6875rem",
            fontWeight: 600,
            letterSpacing: "0.07em",
            textTransform: "uppercase",
            color: "var(--subtle)",
          }}
          title="Mapped to the OWASP Top 10 for LLM apps (2025) and Agentic AI (2026)."
        >
          {meta.owasp}
        </span>
        <span
          style={{
            display: "block",
            marginTop: "0.5rem",
            fontSize: "0.875rem",
            lineHeight: 1.55,
            color: "var(--muted)",
          }}
        >
          {meta.scenario}
        </span>
      </span>

      <span
        aria-hidden
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 22,
          height: 22,
          flexShrink: 0,
          borderRadius: "50%",
          background: enabled ? "var(--accent)" : "transparent",
          border: `1.5px solid ${enabled ? "var(--accent)" : "var(--border-strong)"}`,
          transition: "background .18s ease, border-color .18s ease",
        }}
      >
        {enabled && <Check size={13} strokeWidth={3} color="#fff" />}
      </span>
    </button>
  );
}
