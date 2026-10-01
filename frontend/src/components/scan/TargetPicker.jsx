import React from "react";
import { targetOptions } from "../../lib/targets";

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

/**
 * One question, one answer: which model do we run the attacks against?
 *
 * This replaces the old pair of overlapping controls (a Demo/Real switch AND a
 * separate backend chooser that also offered "Demo / hosted"), which asked the
 * same thing twice and could disagree with itself.
 */
export default function TargetPicker({
  target,
  onChange,
  capabilities = null,
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
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
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
                  <span
                    style={{
                      width: 9,
                      height: 9,
                      borderRadius: "50%",
                      background: "var(--accent)",
                    }}
                  />
                )}
              </span>
              <span style={{ minWidth: 0 }}>
                <span
                  style={{
                    display: "block",
                    fontSize: "0.9375rem",
                    fontWeight: 600,
                    color: "var(--text)",
                  }}
                >
                  {opt.title}
                </span>
                <span
                  style={{
                    display: "block",
                    marginTop: "0.1rem",
                    fontSize: "0.8125rem",
                    color: "var(--muted)",
                    lineHeight: 1.5,
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

            {opt.id === "ollama" && on && (
              <div style={{ padding: "0.75rem 0 0.25rem 2.6rem" }}>
                {models.length > 0 ? (
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
                ) : (
                  <input
                    value={targetModel}
                    onChange={(e) => setTargetModel(e.target.value)}
                    placeholder="llama3.2:1b"
                    aria-label="Ollama model name"
                    style={MODEL_FIELD}
                  />
                )}
                {models.length === 0 && (
                  <p
                    style={{
                      marginTop: "0.5rem",
                      fontSize: "0.8125rem",
                      color: "var(--subtle)",
                      lineHeight: 1.55,
                    }}
                  >
                    Run <code>ollama serve</code> and{" "}
                    <code>ollama pull {targetModel || "llama3.2:1b"}</code> first.
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
      {capabilities && !capabilities.local_backends_enabled && <RunLocallyNote />}
    </div>
  );
}

// On the hosted demo, live targets are one install away: say how, once, and link the full setup.
function RunLocallyNote() {
  return (
    <aside
      aria-label="Run it locally"
      style={{
        marginTop: "0.75rem",
        padding: "0.9rem 1rem",
        borderRadius: "0.6rem",
        border: "1px solid var(--border)",
        background: "var(--surface-2)",
        fontSize: "0.875rem",
        color: "var(--muted)",
        lineHeight: 1.55,
      }}
    >
      <p style={{ color: "var(--text)", fontWeight: 600 }}>Test a live model on your machine</p>
      <pre
        style={{
          margin: "0.5rem 0",
          padding: "0.6rem 0.75rem",
          borderRadius: "0.4rem",
          background: "var(--bg)",
          border: "1px solid var(--border)",
          fontSize: "0.8125rem",
          color: "var(--text)",
          overflowX: "auto",
        }}
      >
        <code>{'pip install "fusion-safety[serve]"\nfusion serve'}</code>
      </pre>
      <p>
        The same page opens locally with these options enabled: Ollama (free), your own OpenAI-compatible server, or a
        hosted API on your own key.{" "}
        <a href="/use#local" className="text-link">
          Run it locally
        </a>
      </p>
    </aside>
  );
}
