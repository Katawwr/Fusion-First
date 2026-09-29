import React from "react";
import { Link } from "react-router-dom";
import { Terminal, Plug, ShieldCheck } from "lucide-react";

// Replaces the old pricing section: there are no accounts and no paid plans. The web demo is
// keyless; real runs happen on your own machine, with your local models and your own Claude
// subscription — never a metered API key.
const WAYS = [
  {
    icon: ShieldCheck,
    title: "Demo scan",
    body: "Uses canned responses. The report is an example, not a measurement.",
  },
  {
    icon: Terminal,
    title: "Run it locally",
    body: "Test your prompt on a local open-weight model through Ollama, graded by your coding agent or the claude CLI.",
  },
  {
    icon: Plug,
    title: "In your agent workflow",
    body: "A Claude Code plugin, an MCP server and a CLI let a coding agent test the prompt it just wrote and add the runtime guardrail.",
  },
];

export default function LocalFirstSection() {
  return (
    <section id="local-first-section" style={{ padding: "clamp(3rem, 8vw, 5rem) 0" }}>
      <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "0 1rem" }}>
        <h2
          style={{
            textAlign: "center",
            fontSize: "clamp(1.6rem, 4vw, 2.2rem)",
            margin: "0 0 2.5rem",
            color: "var(--text)",
          }}
        >
          Free and local-first
        </h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: "1rem",
          }}
        >
          {WAYS.map((way) => {
            const Icon = way.icon;
            const { title, body } = way;
            return (
            <div
              key={title}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "1rem",
                padding: "1.25rem",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <Icon size={22} color="var(--accent)" />
              <h3 style={{ margin: "0.75rem 0 0.4rem", fontSize: "1.05rem", color: "var(--text)" }}>
                {title}
              </h3>
              <p style={{ margin: 0, color: "var(--muted)", fontSize: "0.92rem" }}>{body}</p>
            </div>
            );
          })}
        </div>
        <div style={{ textAlign: "center", marginTop: "2rem" }}>
          <Link
            to="/scan"
            style={{
              display: "inline-block",
              padding: "0.75rem 1.5rem",
              background: "linear-gradient(to right, #f38f95, #db418b)",
              borderRadius: "0.6rem",
              color: "#fff",
              fontWeight: "bold",
              textDecoration: "none",
            }}
          >
            Run the demo scan
          </Link>
          <Link
            to="/use"
            style={{
              display: "inline-block",
              marginLeft: "0.75rem",
              padding: "0.75rem 1.5rem",
              border: "1px solid var(--border)",
              borderRadius: "0.6rem",
              color: "var(--text)",
              fontWeight: "bold",
              textDecoration: "none",
            }}
          >
            Local setup
          </Link>
        </div>
      </div>
    </section>
  );
}
