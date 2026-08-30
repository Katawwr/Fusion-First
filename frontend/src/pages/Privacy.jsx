import React from "react";
import { Helmet } from "react-helmet-async";
import useReveal from "../hooks/useReveal";

export default function Privacy() {
  const [pageRef, isVisible] = useReveal();


  return (
    <>
      <Helmet>
        <title>Privacy &amp; Terms | Fusion First</title>
        <meta
          name="description"
          content="Privacy policy and terms of service for Fusion First. How we handle your data and system prompts."
        />
        <meta
          name="keywords"
          content="Fusion First privacy policy, AI agent evaluation terms, terms of service, data privacy"
        />
        <meta property="og:title" content="Privacy Policy - Fusion First" />
        <meta
          property="og:description"
          content="Privacy policy and terms of service for Fusion First."
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
              backdropFilter: "blur(10px)",
              transition: "border-color 0.2s ease",
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.borderColor = "#66c4e1")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.borderColor = "rgba(102, 196, 225, 0.2)")
            }
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
              Privacy Policy & Terms of Service
            </h1>

            <div style={{ color: "var(--text)", lineHeight: 1.7 }}>
              {/* Privacy Policy */}
              <section style={{ marginBottom: "2rem" }}>
                <h2
                  style={{
                    fontSize: "clamp(1.25rem, 3vw, 1.5rem)",
                    fontWeight: "bold",
                    color: "var(--accent-ink)",
                    marginBottom: "1rem",
                  }}
                >
                  Privacy Policy
                </h2>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "1rem",
                  }}
                >
                  {/* Email & Data Collection */}
                  <div
                    style={{
                      background: "var(--accent-soft)",
                      border: "1px solid var(--border)",
                      borderRadius: "0.5rem",
                      padding: "1rem",
                    }}
                  >
                    <p
                      style={{
                        color: "var(--accent-ink)",
                        fontWeight: "bold",
                        marginBottom: "0.5rem",
                      }}
                    >
                      Email Address & Data Minimization
                    </p>
                    <p style={{ marginBottom: "0.5rem" }}>
                      <strong>Email Address:</strong> We collect your email
                      address solely for authentication purposes (sending
                      sign-in links) and to associate your subscription
                      purchases. We do not share your email with third parties
                      for marketing unless you explicitly opt in.
                    </p>
                    <p style={{ marginBottom: "0.5rem" }}>
                      <strong>Marketing Communications:</strong> We will only
                      send marketing emails if you explicitly opt in during or
                      after account creation. You can opt out at any time by
                      contacting support.
                    </p>
                    <p>
                      <strong>Data Minimization:</strong> We store only the
                      minimum data necessary to provide our service: your email,
                      account creation date, last login time, and subscription
                      status. We do not collect or store unnecessary personal
                      information.
                    </p>
                  </div>

                  <p>
                    <strong>API Security:</strong> Fusion First uses secure
                    server-side API calls. Your system prompts are processed
                    temporarily and never stored permanently.
                  </p>
                  <p>
                    <strong>System Prompts:</strong> Your system prompts are
                    processed temporarily to generate quality tests and fixes.
                    They are not permanently stored on our servers.
                  </p>
                  <p>
                    <strong>Test Results:</strong> Test results are displayed to
                    you in real-time but are not permanently stored or
                    associated with your account unless you explicitly save
                    them.
                  </p>
                  <p>
                    <strong>Payment Information:</strong> Payment processing is
                    handled securely through Lemon Squeezy. Fusion First does
                    not store your credit card information. Subscription and
                    billing details are managed entirely by Lemon Squeezy.
                  </p>
                  <p>
                    <strong>License Keys:</strong> Your license key is stored
                    locally on your device (browser localStorage) to maintain
                    your session. License keys are validated against our server
                    to track credit usage. We store license key identifiers and
                    associated credit balances on our servers.
                  </p>
                  <p>
                    <strong>Analytics:</strong> We collect anonymous usage
                    statistics to improve our service. No personally
                    identifiable information is collected without your consent.
                  </p>
                </div>
              </section>

              {/* Terms of Service */}
              <section style={{ marginBottom: "2rem" }}>
                <h2
                  style={{
                    fontSize: "clamp(1.25rem, 3vw, 1.5rem)",
                    fontWeight: "bold",
                    color: "var(--accent-ink)",
                    marginBottom: "1rem",
                  }}
                >
                  Terms of Service
                </h2>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "1rem",
                  }}
                >
                  <p>
                    <strong>Service Description:</strong> Fusion First is an LLM
                    quality testing platform that helps identify instruction
                    adherence issues, tone inconsistencies, and quality
                    improvements for Large Language Model system prompts.
                  </p>

                  {/* AI Limitations Warning */}
                  <div
                    style={{
                      background: "color-mix(in srgb, var(--danger) 10%, transparent)",
                      border: "1px solid color-mix(in srgb, var(--danger) 35%, transparent)",
                      borderRadius: "0.5rem",
                      padding: "1rem",
                    }}
                  >
                    <p
                      style={{
                        color: "var(--danger)",
                        fontWeight: "bold",
                        marginBottom: "0.5rem",
                      }}
                    >
                      AI Limitations & No Guarantees
                    </p>
                    <p style={{ marginBottom: "0.5rem" }}>
                      Large Language Models (LLMs) are probabilistic systems
                      that can produce unexpected outputs. While Fusion First
                      tests for common quality issues, it DOES NOT guarantee:
                    </p>
                    <ul
                      style={{
                        listStyle: "disc",
                        paddingLeft: "1.5rem",
                        marginBottom: "0.75rem",
                      }}
                    >
                      <li>100% accuracy in quality issue detection</li>
                      <li>
                        Perfect system prompt quality after applying fixes
                      </li>
                      <li>Detection of all possible quality improvements</li>
                      <li>
                        That future AI model updates will not introduce new
                        issues
                      </li>
                    </ul>
                    <p style={{ fontWeight: "600" }}>
                      AI systems are inherently unpredictable. You are
                      responsible for thoroughly testing and monitoring your AI
                      systems in production.
                    </p>
                  </div>

                  <p>
                    <strong>Usage Restrictions:</strong> You agree to use Fusion
                    First only for testing your own LLM systems or systems you
                    have explicit permission to test. Unauthorized testing of
                    third-party systems is prohibited.
                  </p>

                  {/* Credits & Subscriptions */}
                  <div
                    style={{
                      background: "var(--accent-soft)",
                      border: "1px solid var(--border)",
                      borderRadius: "0.5rem",
                      padding: "1rem",
                    }}
                  >
                    <p
                      style={{
                        color: "var(--accent-ink)",
                        fontWeight: "bold",
                        marginBottom: "0.5rem",
                      }}
                    >
                      Credits & Subscriptions
                    </p>
                    <ul style={{ listStyle: "disc", paddingLeft: "1.5rem" }}>
                      <li style={{ marginBottom: "0.5rem" }}>
                        <strong>Credits:</strong> Each scan consumes 1 credit.
                        Credits are included with your subscription plan
                        (Starter: 25/month, Pro: 75/month, Team: 250/month).
                      </li>
                      <li style={{ marginBottom: "0.5rem" }}>
                        <strong>Monthly Reset:</strong> Credits reset at the
                        beginning of each billing cycle. Unused credits do not
                        roll over to the next month.
                      </li>
                      <li style={{ marginBottom: "0.5rem" }}>
                        <strong>Free Trial:</strong> New users receive 2 free
                        credits to try the service. Free credits do not renew.
                      </li>
                      <li style={{ marginBottom: "0.5rem" }}>
                        <strong>License Keys:</strong> Upon purchase, you
                        receive a license key to activate your subscription.
                        Keep your license key secure; it grants access to your
                        credits.
                      </li>
                      <li style={{ marginBottom: "0.5rem" }}>
                        <strong>Refunds:</strong> Subscription refunds are
                        handled according to Lemon Squeezy's refund policy.
                        Contact support for billing issues.
                      </li>
                      <li>
                        <strong>Cancellation:</strong> You may cancel your
                        subscription at any time through Lemon Squeezy. Access
                        continues until the end of your current billing period.
                      </li>
                    </ul>
                  </div>

                  <p>
                    <strong>Limitation of Liability:</strong> Fusion First
                    provides LLM quality testing tools "as is" without
                    warranties. We are not liable for damages resulting from use
                    of our service, implementation of suggested improvements, or
                    quality issues in your AI systems.
                  </p>
                  <p>
                    <strong>General AI Safety Notice:</strong> AI systems can
                    make mistakes, produce biased outputs, hallucinate
                    information, or behave unpredictably. Always implement
                    proper monitoring, human oversight, and failsafes in
                    production AI systems.
                  </p>
                  <p>
                    <strong>Changes to Terms:</strong> We reserve the right to
                    modify these terms at any time. Continued use of the service
                    constitutes acceptance of updated terms.
                  </p>
                </div>
              </section>

              {/* Contact */}
              <section>
                <h2
                  style={{
                    fontSize: "clamp(1.25rem, 3vw, 1.5rem)",
                    fontWeight: "bold",
                    color: "var(--accent-ink)",
                    marginBottom: "1rem",
                  }}
                >
                  Contact
                </h2>
                <p>
                  For questions about privacy, terms, or safety, contact:{" "}
                  <a
                    href="mailto:support-fusion@proton.me"
                    style={{ color: "var(--accent-ink)", fontWeight: "bold" }}
                  >
                    support-fusion@proton.me
                  </a>
                </p>
                <p style={{ fontSize: "0.875rem", marginTop: "0.5rem" }}>
                  Last updated: February 2026
                </p>
              </section>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
