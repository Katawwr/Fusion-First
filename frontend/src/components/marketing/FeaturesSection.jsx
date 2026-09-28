import React from "react";
import useReveal from "../../hooks/useReveal";
import evidence from "../../content/evidence.json";
import { guardrailDescription } from "../../lib/evidence";
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
    title: "One grader for safety and quality",
    description:
      "Safety checks attack the agent; quality checks score instruction following and correctness.",
  },
  {
    icon: Cpu,
    title: "Any model or workflow",
    description:
      "Ollama and any Hugging Face GGUF, your own vLLM or TGI server, OpenAI, Anthropic and other hosted APIs with your key, or any agent through a command adapter.",
  },
  {
    icon: BarChart3,
    title: "A measured grader",
    description:
      "The grader scores each response against a written rubric. Its accuracy on known-answer cases is measured and shown on every report.",
  },
  {
    icon: GitBranch,
    title: "Paired before/after",
    description:
      "The same attacks run against your prompt as written and with the fix, compared with a paired McNemar test. The PROVEN / PRELIMINARY / INCONCLUSIVE badge claims no lift the data can't support.",
  },
  {
    icon: Target,
    title: "OWASP-mapped checks",
    description:
      "Prompt injection, excessive agency, data exfiltration and system prompt leakage, mapped to the OWASP Top 10 for LLMs (2025) and for Agentic AI (2026).",
  },
  {
    icon: RefreshCw,
    title: "Prompt fix and runtime guardrail",
    description: guardrailDescription(evidence.runtime_guardrail),
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
            How Fusion works
          </h2>
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
