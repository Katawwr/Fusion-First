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
        <title>Fusion First: Safety and quality evals for AI agents</title>
        <meta
          name="description"
          content="Fusion First attacks your AI agent, grades safety and quality with a grader measured against known answers, and re-tests a prompt fix on your model. Every rate carries a confidence interval. Built for open-weight models."
        />
        <meta
          name="keywords"
          content="AI agent evaluation, LLM safety testing, LLM quality evals, prompt injection testing, OWASP LLM Top 10, agentic AI security, open-weight model testing, Ollama, Llama safety, LLM red teaming, AI guardrails, instruction following, safety report card"
        />
        <meta
          property="og:title"
          content="Fusion First: Safety and quality evals for AI agents"
        />
        <meta
          property="og:description"
          content="Attack your AI agent, grade safety and quality with a measured grader, and re-test a prompt fix on your model. Built for open-weight models."
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
          content="Fusion First: Safety and quality evals for AI agents"
        />
        <meta
          name="twitter:description"
          content="Attack your AI agent, grade safety and quality with a measured grader, and re-test a prompt fix on your model. Built for open-weight models."
        />
        <link rel="canonical" href="https://fusion-first-testing.com" />
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            name: "Fusion First",
            description:
              "Safety and quality evaluation engine for AI agents. Attacks the agent, grades transcripts with a grader whose accuracy is measured, and re-tests a prompt fix on the user's model. Built for open-weight models.",
            applicationCategory: "DeveloperApplication",
            operatingSystem: "Web",
            offers: {
              "@type": "Offer",
              price: "0",
              priceCurrency: "USD",
              description:
                "Free demo scan and local testing with your own open-weight models",
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
