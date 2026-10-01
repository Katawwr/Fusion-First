import React from "react";
import { runsLocalModels, targetOptions } from "../../lib/targets";

const MODEL_FIELD = {
  width: "100%",
  maxWidth: "20rem",
  borderRadius: "0.65rem",
  border: "1px solid var(--border)",
  background: "var(--surface-2)",
  padding: "0.55rem 0.8rem",
  fontFamily: "'JetBrains Mono', ui-monospace, 'SF Mono', monospace",
  fontSize: "0.8125rem",
  color: "var(--text)",
  outline: "none",
};

const CODE = { fontSize: "0.8125rem", color: "var(--text)" };

// Which model the attacks run against. `checking`: the server hasn't said yet what it can run.
export default function TargetPicker({
  target,
  onChange,
  capabilities = null,
  checking = false,
  targetModel,
  setTargetModel,
  targetSpec = "",
  setTargetSpec = () => {},
  graderSpec = "claude-cli",
  setGraderSpec = () => {},
}) {
  const OPTIONS = targetOptions(capabilities);
  const models = (capabilities && capabilities.ollama_models) || [];

  return (
    <div role="radiogroup" aria-label="Target model" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {OPTIONS.map((opt) => {
        const on = target === opt.id;
        return (
          <div key={opt.id}>
            <button
              type="button"
              role="radio"
              aria-checked={on}
              disabled={opt.disabled}
              onClick={() => onChange(opt.id)}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.75rem",
                width: "100%",
                textAlign: "left",
                padding: "0.85rem 1rem",
                borderRadius: "0.85rem",
                border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`,
                background: on ? "var(--accent-soft)" : "transparent",
                cursor: opt.disabled ? "not-allowed" : "pointer",
                opacity: opt.disabled ? 0.5 : 1,
                transition: "all .18s ease",
              }}
            >
              <span
                aria-hidden
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 18,
                  height: 18,
                  flexShrink: 0,
                  marginTop: "0.15rem",
                  borderRadius: "50%",
                  border: `1.5px solid ${on ? "var(--accent)" : "var(--border-strong)"}`,
                }}
              >
                {on && (
                  <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--accent)" }} />
                )}
              </span>
              <span style={{ minWidth: 0 }}>
                <span style={{ display: "block", fontSize: "0.9375rem", fontWeight: 600, color: "var(--text)" }}>
                  {opt.title}
                </span>
                <span
                  style={{
                    display: "block",
                    marginTop: "0.1rem",
                    fontSize: "0.8125rem",
                    color: "var(--muted)",
                    lineHeight: 1.5,
                    overflowWrap: "anywhere",
                  }}
                >
                  {opt.note}
                </span>
              </span>
            </button>

            {opt.id === "spec" && on && (
              <div style={{ padding: "0.75rem 0 0.25rem 2.6rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <input
                  value={targetSpec}
                  onChange={(e) => setTargetSpec(e.target.value)}
                  placeholder="openai:gpt-4o-mini"
                  aria-label="Target spec"
                  style={MODEL_FIELD}
                />
                <input
                  value={graderSpec}
                  onChange={(e) => setGraderSpec(e.target.value)}
                  placeholder="claude-cli"
                  aria-label="Grader spec"
                  style={MODEL_FIELD}
                />
              </div>
            )}

            {/* The option is enabled only once Ollama reports at least one pulled model. */}
            {opt.id === "ollama" && on && models.length > 0 && (
              <div style={{ padding: "0.75rem 0 0.25rem 2.6rem" }}>
                <select
                  value={models.includes(targetModel) ? targetModel : models[0]}
                  onChange={(e) => setTargetModel(e.target.value)}
                  aria-label="Ollama model"
                  style={MODEL_FIELD}
                >
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        );
      })}
      {!checking && !runsLocalModels(capabilities) && (
        <p style={{ margin: "0.25rem 0 0", fontSize: "0.875rem", color: "var(--muted)", lineHeight: 1.7 }}>
          Live models:{" "}
          <code style={CODE}>pip install "fusion-safety[serve]"</code>, then{" "}
          <code style={CODE}>fusion serve</code>.{" "}
          <a href="/use#local" className="text-link">
            Run it locally
          </a>
        </p>
      )}
    </div>
  );
}
