import React from "react";
import { Helmet } from "react-helmet-async";
import useReveal from "../hooks/useReveal";

// Describes the REAL data flows (no accounts, no payments, no analytics). Keep this page in sync
// with app/ (in-memory scan store) and fusion/ (local-only live backends) when either changes.

const h2 = {
  fontSize: "clamp(1.25rem, 3vw, 1.5rem)",
  fontWeight: "bold",
  color: "var(--accent-ink)",
  marginBottom: "1rem",
};

const callout = {
  background: "var(--accent-soft)",
  border: "1px solid var(--border)",
  borderRadius: "0.5rem",
  padding: "1rem",
};

function Item({ title, children }) {
  return (
    <p>
      <strong>{title}:</strong> {children}
    </p>
  );
}

export default function Privacy() {
  const [pageRef, isVisible] = useReveal();

  return (
    <>
      <Helmet>
        <title>Privacy &amp; Terms | Fusion First</title>
        <meta
          name="description"
          content="How Fusion First handles your system prompts: no accounts, no payments, no analytics. Live testing runs on your own machine."
        />
        <meta property="og:title" content="Privacy & Terms - Fusion First" />
        <meta
          property="og:description"
          content="No accounts, no payments, no analytics. Live testing runs on your own machine."
        />
        <meta property="og:type" content="website" />
        <link rel="canonical" href="https://fusion-first-testing.com/privacy" />
      </Helmet>

      <div
        ref={pageRef}
        style={{
          padding: "4rem 1rem",
          opacity: isVisible ? 1 : 0,
          transform: isVisible ? "translateY(0)" : "translateY(30px)",
          transition: "opacity 0.6s ease-out, transform 0.6s ease-out",
        }}
      >
        <div style={{ maxWidth: "900px", margin: "0 auto" }}>
          <div
            style={{
              padding: "clamp(1.5rem, 4vw, 2.5rem)",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "1rem",
            }}
          >
            <h1
              style={{
                fontSize: "clamp(1.875rem, 5vw, 2.5rem)",
                fontWeight: "bold",
                marginBottom: "2rem",
                background: "linear-gradient(to right, #66c4e1, #f38f95)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              Privacy & Terms
            </h1>

            <div style={{ color: "var(--text)", lineHeight: 1.7 }}>
              <section style={{ marginBottom: "2rem" }}>
                <h2 style={h2}>Privacy</h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={callout}>
                    <p style={{ color: "var(--accent-ink)", fontWeight: "bold", marginBottom: "0.5rem" }}>
                      The short version
                    </p>
                    <p style={{ margin: 0 }}>
                      There are no accounts, no payments and no analytics or tracking. Real
                      (live) testing runs on your own machine, with your own local models and
                      your own Claude subscription.
                    </p>
                  </div>

                  <Item title="Demo scans on this website">
                    The system prompt you paste is sent to the Fusion server to run the demo.
                    Demo responses are canned examples — your prompt is not sent to any AI model.
                    The finished report is kept in the server's memory so its link works, is
                    never written to a database, and disappears when the server restarts.
                  </Item>
                  <Item title="Local use (CLI, MCP server, local web app)">
                    When you run Fusion yourself, your prompts and results stay on your machine.
                    Live tests call only the backends you choose: a local open-weight model via
                    Ollama, and/or the Claude CLI signed in to your own subscription (whose use is
                    governed by Anthropic's terms). Fusion never uses a metered API key unless you
                    explicitly opt in.
                  </Item>
                  <Item title="Stored in your browser">
                    Only your light/dark theme preference (localStorage). No cookies are set for
                    tracking.
                  </Item>
                  <Item title="Training">
                    Fusion does not train any model on your prompts or results.
                  </Item>
                </div>
              </section>

              <section style={{ marginBottom: "2rem" }}>
                <h2 style={h2}>Terms</h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <Item title="What Fusion is">
                    An evaluation engine that tests AI agents for safety (for example prompt
                    injection, data exfiltration, excessive agency and system-prompt leakage)
                    and quality, and suggests fixes. Every reported number carries its sample
                    size and a confidence interval or an honesty badge.
                  </Item>

                  <div
                    style={{
                      background: "color-mix(in srgb, var(--danger) 10%, transparent)",
                      border: "1px solid color-mix(in srgb, var(--danger) 35%, transparent)",
                      borderRadius: "0.5rem",
                      padding: "1rem",
                    }}
                  >
                    <p style={{ color: "var(--danger)", fontWeight: "bold", marginBottom: "0.5rem" }}>
                      Limits & no guarantees
                    </p>
                    <p style={{ marginBottom: "0.5rem" }}>
                      AI models are probabilistic. Fusion measures how often attacks land and how
                      accurate its own judge is, but it DOES NOT guarantee:
                    </p>
                    <ul style={{ listStyle: "disc", paddingLeft: "1.5rem", marginBottom: "0.75rem" }}>
                      <li>100% accuracy in quality issue detection</li>
                      <li>That a hardened prompt stops every attack</li>
                      <li>That untested attacks or future model versions behave the same way</li>
                    </ul>
                    <p style={{ fontWeight: "600", margin: 0 }}>
                      You remain responsible for testing, monitoring and human oversight of your AI
                      systems in production.
                    </p>
                  </div>

                  <Item title="Acceptable use">
                    Test only AI systems you own or have explicit permission to test.
                  </Item>
                  <Item title="Liability">
                    Fusion First is provided "as is" without warranties. We are not liable for
                    damages arising from its use or from changes you make based on its results.
                  </Item>
                  <Item title="Changes">
                    We may update these terms; continued use means you accept the updated terms.
                  </Item>
                </div>
              </section>

              <section>
                <h2 style={h2}>Contact</h2>
                <p>
                  Questions about privacy, terms or safety:{" "}
                  <a
                    href="mailto:support-fusion@proton.me"
                    style={{ color: "var(--accent-ink)", fontWeight: "bold" }}
                  >
                    support-fusion@proton.me
                  </a>
                </p>
                <p style={{ fontSize: "0.875rem", marginTop: "0.5rem" }}>Last updated: September 2026</p>
              </section>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
