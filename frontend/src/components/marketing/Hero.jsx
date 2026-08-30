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

  const scrollToPricing = () => {
    const pricingSection = document.getElementById("pricing-section");
    if (pricingSection) {
      pricingSection.scrollIntoView({ behavior: "smooth" });
    }
  };

  // Real evidence from the testing phase, the same attack suite run against two models, judged by
  // a calibrated examiner (F1 1.00 vs a known-answer set). This is the thesis: frontier models
  // resist, open-weight models don't, and Fusion measures exactly where.
  const evidence = [
    {
      model: "Claude Haiku",
      kind: "frontier",
      stat: "0% got through",
      verdict: "Robust",
      tone: "var(--ok)",
    },
    {
      model: "Llama 3.2 (1B)",
      kind: "open-weight",
      stat: "62% injection · 67% data-leak",
      verdict: "Exposed",
      tone: "var(--danger)",
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
              onClick={scrollToPricing}
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
              View Pricing
            </button>
          </div>

          {/* Evidence signature, real measured proof, in the shape of the product's own output */}
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
              The same attack suite, two models
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
              Graded by a calibrated examiner that scores{" "}
              <strong style={{ color: "var(--text)" }}>F1&nbsp;1.00</strong>{" "}
              against a known-answer set. Frontier models resist; open-weight
              models don't, Fusion measures exactly where.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
