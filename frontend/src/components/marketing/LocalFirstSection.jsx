import React from "react";
import { Link } from "react-router-dom";
import { Terminal, Plug, ShieldCheck } from "lucide-react";

// Replaces the old pricing section: there are no accounts and no paid plans. The web demo is
// keyless; real runs happen on your own machine, with your local models and your own Claude
// subscription — never a metered API key.
const WAYS = [
  {
    icon: ShieldCheck,
    title: "Try it here",
    body: "The demo scan runs instantly with no signup. Its responses are canned examples, clearly labelled, so you can see exactly what a report tells you.",
  },
  {
    icon: Terminal,
    title: "Run it locally",
    body: "Test your own prompt against a local open-weight model through Ollama, graded by your coding agent or a local model. Free, private, no API key.",
  },
  {
    icon: Plug,
    title: "Use it inside your agent workflow",
    body: "A Claude Code plugin, an MCP server and a CLI let a coding agent test, fix and guard the prompt it just wrote, without leaving the editor.",
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
            margin: "0 0 0.75rem",
            color: "var(--text)",
          }}
        >
          Free and local-first
        </h2>
        <p
          style={{
            textAlign: "center",
            color: "var(--muted)",
            maxWidth: "640px",
            margin: "0 auto 2.5rem",
          }}
        >
          No accounts, no credits, no metered API keys. Real testing runs on your
          machine, with your models.
        </p>
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
            How to run it locally
          </Link>
        </div>
      </div>
    </section>
  );
}
