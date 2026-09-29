import React from "react";
import useReveal from "../../hooks/useReveal";
import { useNavigate } from "react-router-dom";
import { Shield } from "lucide-react";

export default function Hero() {
  const [sectionRef, isVisible] = useReveal();
  const navigate = useNavigate();

  const goToTest = () => {
    navigate("/scan");
  };

  const scrollToLocalFirst = () => {
    const section = document.getElementById("local-first-section");
    if (section) {
      section.scrollIntoView({ behavior: "smooth" });
    }
  };

  // What Fusion gives you — the shape of the output, not a result. Numbers appear here ONLY when
  // committed evidence backs them (evals/claims.yaml, enforced by tests/test_claims_backed.py).
  const evidence = [
    {
      model: "Your agent, as written",
      kind: "measured",
      stat: "Graded A–F against real attacks",
      verdict: "Measured",
      tone: "var(--accent)",
    },
    {
      model: "Runtime guardrail",
      kind: "in your agent's code",
      stat: "Blocks leaks and unrequested tool calls",
      verdict: "Measured",
      tone: "var(--accent)",
    },
    {
      model: "Prompt fix",
      kind: "optional",
      stat: "Same attacks, re-tested on your model",
      verdict: "Proven or not",
      tone: "var(--accent)",
    },
  ];

  return (
    <section
      ref={sectionRef}
      style={{
        position: "relative",
        padding: "clamp(3rem, 8vw, 5rem) 0",
        overflow: "hidden",
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? "translateY(0)" : "translateY(30px)",
        transition: "opacity 0.6s ease-out, transform 0.6s ease-out",
      }}
    >
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "0 1rem" }}>
        <div style={{ textAlign: "center" }}>
          {/* Main heading */}
          <h1
            style={{
              fontSize: "clamp(2rem, 6vw, 3.5rem)",
              fontWeight: "bold",
              color: "var(--text)",
              marginBottom: "2.5rem",
              lineHeight: 1.2,
            }}
          >
            <span
              style={{
                background: "linear-gradient(to right, #66c4e1, #f38f95)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              Measure and guard
            </span>{" "}
            AI agents
          </h1>

          {/* CTA buttons */}
          <div
            style={{
              display: "flex",
              flexDirection: "row",
              flexWrap: "wrap",
              alignItems: "center",
              justifyContent: "center",
              gap: "1rem",
              marginBottom: "3rem",
            }}
          >
            <button
              onClick={goToTest}
              style={{
                padding: "0.875rem 2rem",
                background: "linear-gradient(to right, #f38f95, #db418b)",
                border: "none",
                borderRadius: "0.5rem",
                color: "#fff",
                fontWeight: "bold",
                fontSize: "1rem",
                cursor: "pointer",
                transition: "transform 0.2s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-3px)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
              }}
            >
              Scan your agent
            </button>
            <button
              onClick={scrollToLocalFirst}
              style={{
                padding: "0.875rem 2rem",
                background: "transparent",
                border: "2px solid #66c4e1",
                borderRadius: "0.5rem",
                color: "var(--accent-ink)",
                fontWeight: "bold",
                fontSize: "1rem",
                cursor: "pointer",
                transition:
                  "transform 0.2s ease, background 0.2s ease, color 0.2s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-3px)";
                e.currentTarget.style.background = "rgba(102, 196, 225, 0.15)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.background = "transparent";
              }}
            >
              Run it locally
            </button>
          </div>

          {/* The shape of the product's own output (no unbacked numbers — see evals/claims.yaml) */}
          <div
            style={{
              maxWidth: "760px",
              margin: "0 auto",
              background: "var(--surface)",
              border: "1px solid var(--border-strong)",
              borderRadius: "1rem",
              padding: "clamp(1.25rem, 3vw, 1.75rem)",
              boxShadow: "var(--shadow-sm)",
              textAlign: "left",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                fontSize: "0.7rem",
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--subtle)",
                marginBottom: "1rem",
              }}
            >
              <Shield size={13} color="var(--accent)" />
              What you get
            </div>
            {evidence.map((row, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: "0.5rem 1rem",
                  padding: "0.75rem 0",
                  borderTop: i === 0 ? "none" : "1px solid var(--border)",
                }}
              >
                <div style={{ flex: "1 1 160px", minWidth: 0 }}>
                  <div style={{ color: "var(--text)", fontWeight: 600 }}>
                    {row.model}
                  </div>
                  <div style={{ color: "var(--subtle)", fontSize: "0.8rem" }}>
                    {row.kind}
                  </div>
                </div>
                <div
                  style={{
                    flex: "1 1 200px",
                    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                    fontSize: "0.9rem",
                    color: "var(--text)",
                  }}
                >
                  {row.stat}
                </div>
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    letterSpacing: "0.02em",
                    padding: "0.2rem 0.6rem",
                    borderRadius: "9999px",
                    color: row.tone,
                    border: `1px solid ${row.tone}`,
                    background: "transparent",
                    whiteSpace: "nowrap",
                  }}
                >
                  {row.verdict}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
