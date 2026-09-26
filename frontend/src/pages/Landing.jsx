import React from "react";
import { Helmet } from "react-helmet-async";
import {
  Hero,
  FeaturesSection,
  UseCasesSection,
  LocalFirstSection,
} from "../components/marketing";

export default function Landing() {
  return (
    <>
      <Helmet>
        <title>Fusion First: Prove your AI agent is safe and good</title>
        <meta
          name="description"
          content="Fusion First automatically red-teams your AI agent for safety, grades its quality, and hands you a one-click fix. Every number carries a confidence interval and is checked against ground truth. Built for open-weight models, where the risks are real. Free demo, no signup."
        />
        <meta
          name="keywords"
          content="AI agent evaluation, LLM safety testing, LLM quality evals, prompt injection testing, OWASP LLM Top 10, agentic AI security, open-weight model testing, Ollama, Llama safety, LLM red teaming, AI guardrails, instruction following, safety report card"
        />
        <meta
          property="og:title"
          content="Fusion First: Prove your AI agent is safe and good"
        />
        <meta
          property="og:description"
          content="Red-team your agent for safety and grade its quality, automatically. Every number carries a confidence interval, checked against ground truth. Built for open-weight models. Free demo, no signup."
        />
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://fusion-first-testing.com" />
        <meta
          property="og:image"
          content="https://fusion-first-testing.com/og-image.png"
        />
        <meta name="twitter:card" content="summary_large_image" />
        <meta
          name="twitter:title"
          content="Fusion First: Prove your AI agent is safe and good"
        />
        <meta
          name="twitter:description"
          content="Proof-grade safety + quality evals for AI agents, with honest confidence intervals and one-click hardening. Built for open-weight models."
        />
        <link rel="canonical" href="https://fusion-first-testing.com" />
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            name: "Fusion First",
            description:
              "A proof-grade evaluation engine for AI agents, safety and quality. Red-teams your agent, grades its quality against a calibrated judge, and ships a one-click fix. Built for open-weight models.",
            applicationCategory: "DeveloperApplication",
            operatingSystem: "Web",
            offers: {
              "@type": "Offer",
              price: "0",
              priceCurrency: "USD",
              description:
                "Free keyless demo scan; free local testing with your own open-weight models",
            },
          })}
        </script>
      </Helmet>

      {/* Hero Section */}
      <Hero />

      {/* Key Features Section */}
      <FeaturesSection />

      {/* Use Cases Section */}
      <UseCasesSection />

      {/* How to use it — free and local-first (no accounts, no billing) */}
      <LocalFirstSection />
    </>
  );
}
