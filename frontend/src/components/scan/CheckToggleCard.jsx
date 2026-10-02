import React from "react";
import { Check } from "lucide-react";
import { isQualityCheck, metaFor } from "../../lib/jargon";

export default function CheckToggleCard({ check, enabled, onToggle, disabled = false }) {
  const meta = metaFor(check);
  const on = enabled && !disabled;
  return (
    <button
      type="button"
      onClick={() => !disabled && onToggle(check)}
      aria-pressed={on}
      aria-disabled={disabled}
      disabled={disabled}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: "0.875rem",
        alignItems: "start",
        width: "100%",
        height: "100%",
        padding: "1.15rem",
        textAlign: "left",
        borderRadius: "1rem",
        border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`,
        background: "var(--surface)",
        boxShadow: on ? "var(--shadow-sm)" : "none",
        opacity: on ? 1 : disabled ? 0.45 : 0.62,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "border-color .18s ease, opacity .18s ease, box-shadow .18s ease",
      }}
      onMouseEnter={(e) => {
        if (!on && !disabled) e.currentTarget.style.opacity = "0.85";
      }}
      onMouseLeave={(e) => {
        if (!on && !disabled) e.currentTarget.style.opacity = "0.62";
      }}
    >
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
          title={isQualityCheck(check) ? "Graded on normal requests, not attacks."
            : "Mapped to the OWASP Top 10 for LLM apps (2025) and Agentic AI (2026); the ASI (Agentic) codes are provisional."}
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
        {enabled && <Check size={13} strokeWidth={3} color="var(--on-primary)" />}
      </span>
    </button>
  );
}
