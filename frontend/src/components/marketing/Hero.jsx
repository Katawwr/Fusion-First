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

  // The thesis, stated qualitatively: frontier models resist most attacks, open-weight models
  // often don't, and Fusion measures exactly where. Numbers appear here ONLY when committed evidence
  // backs them (evals/claims.yaml, enforced by tests/test_claims_backed.py).
  // What a Fusion report tells you — the shape of the output, not a result. Measured numbers
  // for specific models appear only once committed evidence backs them.
  const evidence = [
    {
      model: "Your prompt, as written",
      kind: "baseline",
      stat: "Graded A–F against real attacks",
      verdict: "Measured",
      tone: "var(--accent)",
    },
    {
      model: "Hardened by Fusion",
      kind: "after the fix",
      stat: "Same attacks, re-tested",
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
          {/* Badge */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.5rem 1rem",
              borderRadius: "9999px",
              background: "var(--surface)",
              border: "1px solid var(--border-strong)",
              marginBottom: "2rem",
            }}
          >
            <span
              style={{
                color: "var(--accent-ink)",
                fontSize: "0.875rem",
                fontWeight: "500",
              }}
            >
              Safety + quality
            </span>
            <span style={{ color: "var(--text)", fontSize: "0.875rem" }}>
              Free demo, no signup
            </span>
          </div>

          {/* Main heading */}
          <h1
            style={{
              fontSize: "clamp(2rem, 6vw, 3.5rem)",
              fontWeight: "bold",
              color: "var(--text)",
              marginBottom: "1.5rem",
              lineHeight: 1.2,
            }}
          >
            Ship AI agents you can{" "}
            <span
              style={{
                background: "linear-gradient(to right, #66c4e1, #f38f95)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              prove
            </span>{" "}
            are safe and good
          </h1>

          {/* Subheading */}
          <p
            style={{
              fontSize: "clamp(1rem, 2.5vw, 1.25rem)",
              color: "var(--text)",
              maxWidth: "820px",
              margin: "0 auto 2.5rem",
              lineHeight: 1.6,
            }}
          >
            Connect your agent or paste its prompt. Fusion red-teams it for
            safety, grades its quality, and hands you the
            fix. Every number carries a confidence interval and is checked
            against a known-answer set. Built for the open-weight models where
            the risks are real.
          </p>

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
              Scan your agent free
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
              What every report tells you
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
            <p
              style={{
                margin: "0.9rem 0 0",
                fontSize: "0.82rem",
                color: "var(--muted)",
                lineHeight: 1.5,
              }}
            >
              Graded by an examiner that is itself{" "}
              <strong style={{ color: "var(--text)" }}>measured against known answers</strong>;
              every report says how far to trust its grade. Fusion measures exactly
              where your model resists and where it gives way.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
