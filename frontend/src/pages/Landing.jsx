import React, { useRef } from 'react';
import { Helmet } from 'react-helmet-async';
import { Hero, PricingSection, FeaturesSection, UseCasesSection } from '../components/marketing';

export default function Landing({
  freeCredits,
  totalCredits,
  isSubscriber,
  userPlan,
}) {
  const pricingRef = useRef(null);

  return (
    <>
      <Helmet>
        <title>Fusion First — Prove your AI agent is safe</title>
        <meta
          name="description"
          content="Fusion First is a test-and-prove engine for agentic AI safety. Paste your bot's system prompt, run an OWASP-mapped attack suite, and get a Safety Report Card with a one-click fix — every number backed by a confidence interval or an honesty badge."
        />
        <meta name="keywords" content="AI agent safety, prompt injection testing, OWASP LLM Top 10, agentic AI security, excessive agency, data exfiltration, system prompt leakage, LLM red teaming, AI guardrails, safety report card" />
        <meta property="og:title" content="Fusion First — Prove your AI agent is safe" />
        <meta
          property="og:description"
          content="Paste your bot's prompt, run an OWASP-mapped attack suite, and get a graded before/after Safety Report Card with a one-click fix. Free demo, no signup."
        />
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://fusion-first-testing.com" />
        <meta property="og:image" content="https://fusion-first-testing.com/og-image.png" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="Fusion First — Prove your AI agent is safe" />
        <meta name="twitter:description" content="An OWASP-mapped test-and-prove engine for agentic AI safety, with one-click hardening." />
        <link rel="canonical" href="https://fusion-first-testing.com" />
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": "Fusion First",
            "description": "A test-and-prove engine for agentic AI safety. Runs an OWASP-mapped attack suite against your bot's system prompt, grades baseline vs hardened, and ships a one-click fix.",
            "applicationCategory": "SecurityApplication",
            "operatingSystem": "Web",
            "offers": {
              "@type": "Offer",
              "price": "0",
              "priceCurrency": "USD",
              "description": "Free demo scan; real scans on paid plans"
            }
          })}
        </script>
      </Helmet>

      {/* Hero Section */}
      <Hero />

      {/* Key Features Section */}
      <FeaturesSection />

      {/* Use Cases Section */}
      <UseCasesSection />

      {/* Pricing Section */}
      <div ref={pricingRef}>
        <PricingSection
          isSubscriber={isSubscriber}
          userPlan={userPlan}
          freeCredits={freeCredits}
          totalCredits={totalCredits}
        />
      </div>

    </>
  );
}
