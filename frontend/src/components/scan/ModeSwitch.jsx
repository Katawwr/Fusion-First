import React from "react";

// Demo (instant, keyless) vs Real (your prompt, real model). A quiet segmented control:
// one hairline track, the selected pill lifted on the card surface.
export default function ModeSwitch({ mode, onChange, liveAvailable }) {
  const opt = (value, title, subtitle, disabled) => {
    const active = mode === value;
    return (
      <button
        key={value}
        type="button"
        disabled={disabled}
        aria-pressed={active}
        onClick={() => onChange(value)}
        style={{
          flex: 1,
          textAlign: "left",
          padding: "0.65rem 0.9rem",
          borderRadius: "0.7rem",
          border: `1px solid ${active ? "var(--accent)" : "transparent"}`,
          background: active ? "var(--surface)" : "transparent",
          boxShadow: active ? "var(--shadow-sm)" : "none",
          color: "inherit",
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.45 : 1,
          transition: "all .18s ease",
        }}
      >
        <span
          style={{
            display: "block",
            fontSize: "0.875rem",
            fontWeight: 600,
            color: active ? "var(--text)" : "var(--muted)",
          }}
        >
          {title}
        </span>
        <span
          style={{
            display: "block",
            fontSize: "0.75rem",
            color: "var(--subtle)",
          }}
        >
          {subtitle}
        </span>
      </button>
    );
  };
  return (
    <div
      style={{
        display: "flex",
        gap: "0.35rem",
        padding: "0.3rem",
        borderRadius: "0.9rem",
        background: "var(--surface-2)",
      }}
    >
      {opt("demo", "Demo scan", "Instant, no signup")}
      {opt(
        "live",
        "Real scan",
        liveAvailable ? "Your prompt, real model" : "Coming soon",
        !liveAvailable,
      )}
    </div>
  );
}
