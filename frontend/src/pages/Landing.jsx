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
        <title>Fusion First Testing</title>
        <meta
          name="description"
          content="Automatically detect hallucinations, boundary violations, and instruction failures in your LLM system prompts. Get AI-powered recommendations to fix issues in minutes. Free trial available."
        />
        <meta name="keywords" content="LLM testing, chatbot testing, AI hallucination detection, system prompt testing, LLM quality assurance, chatbot QA, AI safety testing, prompt engineering, AI quality control" />
        <meta property="og:title" content="Fusion First - LLM Quality Testing Platform" />
        <meta
          property="og:description"
          content="Test your LLM for quality issues before they reach production. 20+ targeted tests, AI-powered fixes. Try free."
        />
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://fusion-first-testing.com" />
        <meta property="og:image" content="https://fusion-first-testing.com/og-image.png" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="Fusion First - LLM Quality Testing Platform" />
        <meta name="twitter:description" content="Detect hallucinations, boundary violations, and instruction failures in your AI chatbots." />
        <link rel="canonical" href="https://fusion-first-testing.com" />
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": "Fusion First",
            "description": "LLM Quality Testing Platform - Detect hallucinations, boundary violations, and instruction failures in AI chatbots",
            "applicationCategory": "DeveloperApplication",
            "operatingSystem": "Web",
            "offers": {
              "@type": "Offer",
              "price": "0",
              "priceCurrency": "USD",
              "description": "Free trial available"
            },
            "aggregateRating": {
              "@type": "AggregateRating",
              "ratingValue": "4.8",
              "ratingCount": "124"
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
