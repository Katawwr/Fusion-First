import React from "react";
import {
  effectiveGrader,
  graderOptions,
  hostedProviders,
  liveSetupHint,
  specPlaceholder,
  targetOptions,
} from "../../lib/targets";

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

const FIELD_LABEL = { display: "block", fontSize: "0.8125rem", color: "var(--muted)", marginBottom: "0.3rem" };
const HINT = { margin: "0.25rem 0 0", fontSize: "0.875rem", color: "var(--muted)", lineHeight: 1.7 };
const SPEND_ENV = "FUSION_ALLOW_API_SPEND=1";

function Code({ children }) {
  return <code className="inline-code">{children}</code>;
}

function WithCode({ text }) {
  const [before, after] = text.split(SPEND_ENV);
  if (after === undefined) return text;
  return (
    <>
      {before}
      <Code>{SPEND_ENV}</Code>
      {after}
    </>
  );
}

// Only graders that can run here: one is stated, several are a choice, and hosted providers (which
// need a model name) make it a typed spec.
function GraderField({ capabilities, graderSpec, setGraderSpec }) {
  const graders = graderOptions(capabilities);
  const hosted = hostedProviders(capabilities);
  const value = effectiveGrader(capabilities, graderSpec);
  if (hosted.length) {
    return (
      <label>
        <span style={FIELD_LABEL}>Grader</span>
        <input
          value={value}
          onChange={(e) => setGraderSpec(e.target.value)}
          placeholder={`${hosted[0]}:<model>`}
          aria-label="Grader spec"
          list="fusion-graders"
          style={MODEL_FIELD}
        />
        <datalist id="fusion-graders">
          {[...graders, ...hosted.map((p) => `${p}:`)].map((g) => (
            <option key={g} value={g} />
          ))}
        </datalist>
      </label>
    );
  }
  if (graders.length > 1) {
    return (
      <label>
        <span style={FIELD_LABEL}>Grader</span>
        <select value={value} onChange={(e) => setGraderSpec(e.target.value)} aria-label="Grader" style={MODEL_FIELD}>
          {graders.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
      </label>
    );
  }
  return (
    <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--muted)" }}>
      Grader <Code>{value}</Code>
    </p>
  );
}

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
  graderSpec = "",
  setGraderSpec = () => {},
}) {
  const OPTIONS = targetOptions(capabilities);
  const models = (capabilities && capabilities.ollama_models) || [];
  const hint = liveSetupHint(capabilities, checking);
  const grader = (
    <GraderField capabilities={capabilities} graderSpec={graderSpec} setGraderSpec={setGraderSpec} />
  );

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
                cursor: "pointer",
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
                {opt.note && (
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
                )}
              </span>
            </button>

            {opt.id === "spec" && on && (
              <div style={{ padding: "0.75rem 0 0.25rem 2.6rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <label>
                  <span style={FIELD_LABEL}>Target</span>
                  <input
                    value={targetSpec}
                    onChange={(e) => setTargetSpec(e.target.value)}
                    placeholder={specPlaceholder(capabilities)}
                    aria-label="Target spec"
                    style={MODEL_FIELD}
                  />
                </label>
                {grader}
              </div>
            )}

            {opt.id === "ollama" && on && models.length > 0 && (
              <div style={{ padding: "0.75rem 0 0.25rem 2.6rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
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
                {grader}
              </div>
            )}
          </div>
        );
      })}
      {hint?.kind === "install" && (
        <p style={HINT}>
          Live models: <Code>pip install "fusion-safety[serve]"</Code>, then <Code>fusion serve</Code>.{" "}
          <a href="/use#local" className="text-link">
            Run Locally
          </a>
        </p>
      )}
      {hint?.kind === "grader" && (
        <p style={HINT}>
          <WithCode text={hint.text} />{" "}
          <a href="/use#local" className="text-link">
            Setup
          </a>
        </p>
      )}
    </div>
  );
}
