import React from "react";

const TIERS = [
  { id: "quick", label: "Quick", detail: "8 attacks per check" },
  { id: "full", label: "Full", detail: "18–24 attacks per check" },
];

export default function TierPicker({ tier, onChange }) {
  return (
    <div role="radiogroup" aria-label="Attack set" style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
      {TIERS.map((t) => {
        const on = tier === t.id;
        return (
          <button
            key={t.id}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(t.id)}
            style={{
              padding: "0.55rem 0.9rem",
              borderRadius: "0.75rem",
              border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`,
              background: on ? "var(--accent-soft)" : "transparent",
              color: "var(--text)",
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            <span style={{ fontWeight: 600 }}>{t.label}</span>
            <span style={{ color: "var(--muted)" }}> · {t.detail}</span>
          </button>
        );
      })}
    </div>
  );
}
