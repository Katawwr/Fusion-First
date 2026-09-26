import React from "react";
import useReveal from "../../hooks/useReveal";
import {
  Cpu,
  Target,
  Layers,
  GitBranch,
  BarChart3,
  RefreshCw,
} from "lucide-react";

const features = [
  {
    icon: Layers,
    title: "Safety and quality, one engine",
    description:
      "Two questions, one calibrated judge. Safety: can your agent be hijacked, leak data, or take actions nobody asked for? Quality: does it follow instructions and stay accurate? Both graded the same honest way.",
  },
  {
    icon: Cpu,
    title: "Built for open-weight models",
    description:
      "Frontier models resist most attacks; open-weight ones don't. Test yours locally and free with Ollama, Llama, Mistral, Qwen, judged by Claude, an examiner from a different model family entirely.",
  },
  {
    icon: BarChart3,
    title: "A calibrated examiner, not a vibe",
    description:
      "An AI judge scores each response against a written rubric, and we measure the judge itself against known-answer cases and report that accuracy with a confidence interval, so you know how far to trust the grade.",
  },
  {
    icon: GitBranch,
    title: "Before and after you can defend",
    description:
      "The same attacks against your prompt as-is and hardened, with a 95% confidence interval and a PROVEN / PRELIMINARY / INCONCLUSIVE badge. We refuse to claim a lift the evidence cannot back.",
  },
  {
    icon: Target,
    title: "Mapped to real threats",
    description:
      "Safety checks map to the OWASP Top 10 for LLMs (2025) and Agentic AI (2026), prompt injection, excessive agency, data exfiltration, secret leakage. The risks the industry actually tracks, not a made-up list.",
  },
  {
    icon: RefreshCw,
    title: "One fix, two layers",
    description:
      "A hardened system prompt plus a runtime guardrail that blocks leaked secrets and unauthorized actions even when the model slips. Copy, paste, done, the fix works everywhere your agent runs.",
  },
];

export default function FeaturesSection() {
  const [sectionRef, isVisible] = useReveal();

  return (
    <section
      ref={sectionRef}
      style={{
        padding: "clamp(3rem, 6vw, 5rem) 0",
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? "translateY(0)" : "translateY(30px)",
        transition: "opacity 0.6s ease-out, transform 0.6s ease-out",
      }}
    >
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "0 1rem" }}>
        {/* Section header */}
        <div style={{ textAlign: "center", marginBottom: "3rem" }}>
          <h2
            style={{
              fontSize: "clamp(1.75rem, 4vw, 2.5rem)",
              fontWeight: "bold",
              color: "var(--text)",
              marginBottom: "1rem",
            }}
          >
            Proof, not vibes
          </h2>
          <p
            style={{
              fontSize: "1.125rem",
              color: "var(--text)",
              maxWidth: "700px",
              margin: "0 auto",
              lineHeight: 1.6,
            }}
          >
            Anyone can say your agent is "safe" or "good." Fusion measures both,
            against real threats and known answers, with statistics that admit
            their own uncertainty.
          </p>
        </div>

        {/* Features grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
            gap: "1.5rem",
          }}
        >
          {features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <div
                key={index}
                className="feature-card"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "1rem",
                  padding: "1.5rem",
                  backdropFilter: "blur(10px)",
                  opacity: isVisible ? 1 : 0,
                  transform: isVisible ? "translateY(0)" : "translateY(20px)",
                  transition: `opacity 0.5s ease-out ${index * 0.1}s, transform 0.5s ease-out ${index * 0.1}s, border-color 0.3s ease`,
                  cursor: "default",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "#66c4e1";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--border)";
                }}
              >
                <div
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "0.75rem",
                    background:
                      "linear-gradient(135deg, var(--border), rgba(243, 143, 149, 0.2))",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginBottom: "1rem",
                  }}
                >
                  <Icon size={24} color="#66c4e1" />
                </div>
                <h3
                  style={{
                    fontSize: "1.125rem",
                    fontWeight: "600",
                    color: "var(--text)",
                    marginBottom: "0.5rem",
                  }}
                >
                  {feature.title}
                </h3>
                <p
                  style={{
                    color: "var(--muted)",
                    fontSize: "0.9rem",
                    lineHeight: 1.6,
                  }}
                >
                  {feature.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
