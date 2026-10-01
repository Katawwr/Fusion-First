import React from "react";
import { Helmet } from "react-helmet-async";
import { Doc, DocHeader } from "../components/doc";

// Describes the REAL data flows (no accounts, no payments, no analytics). Keep this page in sync
// with app/ (in-memory scan store) and fusion_first/ (local-only live backends) when either changes.

function Item({ title, children }) {
  return (
    <p>
      <strong>{title}:</strong> {children}
    </p>
  );
}

export default function Privacy() {
  return (
    <>
      <Helmet>
        <title>Privacy &amp; Terms | Fusion First</title>
        <meta
          name="description"
          content="How Fusion First handles your system prompts: no accounts, payments or analytics. Live testing runs on your machine."
        />
        <meta property="og:title" content="Privacy & Terms - Fusion First" />
        <meta
          property="og:description"
          content="No accounts, payments or analytics. Live testing runs on your machine."
        />
        <meta property="og:type" content="website" />
        <link rel="canonical" href="https://fusion-first-testing.com/privacy" />
      </Helmet>

      <Doc>
        <DocHeader title="Privacy & Terms" />
            <div className="prose mt-8">
              <section style={{ marginBottom: "2rem" }}>
                <h2 className="doc-h2 mb-4">Privacy</h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <Item title="Demo scans on this website">
                    Your prompt goes to the Fusion server, never to an AI model; responses are
                    canned. Reports are held in server memory only (no database) and discarded
                    on restart.
                  </Item>
                  <Item title="Local use (CLI, MCP server, local web app)">
                    Prompts and results stay on your machine. Live tests call only the backends
                    you choose; a hosted API needs your own key and FUSION_ALLOW_API_SPEND=1.
                    Each provider&apos;s terms apply.
                  </Item>
                  <Item title="Stored in your browser">
                    Only your light/dark theme preference (localStorage). No tracking cookies.
                  </Item>
                  <Item title="Training">
                    Fusion does not train any model on your prompts or results.
                  </Item>
                </div>
              </section>

              <section style={{ marginBottom: "2rem" }}>
                <h2 className="doc-h2 mb-4">Terms</h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div
                    style={{
                      borderLeft: "2px solid var(--danger)",
                      padding: "0.25rem 0 0.25rem 1rem",
                    }}
                  >
                    <p style={{ color: "var(--danger)", fontWeight: "bold", marginBottom: "0.5rem" }}>
                      Limits & no guarantees
                    </p>
                    <p style={{ marginBottom: "0.5rem" }}>
                      Fusion measures attack rates and grader accuracy. It does not guarantee:
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
                <h2 className="doc-h2 mb-4">Contact</h2>
                <p>
                  Questions about privacy, terms or safety:{" "}
                  <a
                    href="mailto:support-fusion@proton.me"
                    className="text-link"
                  >
                    support-fusion@proton.me
                  </a>
                </p>
                <p style={{ fontSize: "0.875rem", marginTop: "0.5rem" }}>Last updated: September 2026</p>
              </section>
            </div>
      </Doc>
    </>
  );
}
