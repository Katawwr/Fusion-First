import React, { useState, useEffect, useRef } from 'react';
import { Helmet } from 'react-helmet-async';
import { Sparkles } from 'lucide-react';
import { ToolSection } from '../components/tool';

export default function Test({
  freeCredits,
  setFreeCredits,
  totalCredits,
  isSubscriber,
  userPlan,
  toolState,
  setToolState,
  session,
}) {
  const [isVisible, setIsVisible] = useState(false);
  const pageRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.1 }
    );

    if (pageRef.current) {
      observer.observe(pageRef.current);
    }

    return () => observer.disconnect();
  }, []);

  return (
    <>
      <Helmet>
        <title>Fusion First Testing</title>
        <meta
          name="description"
          content="Run quality tests on your LLM system prompts. Detect hallucinations, boundary violations, and instruction failures with 20+ targeted test categories."
        />
        <meta name="keywords" content="LLM testing tool, chatbot quality test, AI prompt testing, hallucination detection tool, system prompt analyzer" />
        <meta property="og:title" content="LLM Quality Testing Tool - Fusion First" />
        <meta property="og:description" content="Test your LLM system prompts for quality issues. 20+ test categories, AI-powered fixes." />
        <meta property="og:type" content="website" />
        <link rel="canonical" href="https://fusion-first-testing.com/test" />
      </Helmet>

      <div
        ref={pageRef}
        style={{
          padding: '2rem 0 4rem',
          opacity: isVisible ? 1 : 0,
          transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
          transition: 'opacity 0.6s ease-out, transform 0.6s ease-out'
        }}
      >
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 1rem' }}>
          {/* Active Subscription Box */}
          {isSubscriber && userPlan && (
            <div style={{
              background: 'rgba(80, 77, 154, 0.25)',
              border: '1px solid rgba(243, 143, 149, 0.3)',
              borderRadius: '0.75rem',
              padding: '0.75rem 1.25rem',
              marginBottom: '1.5rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              backdropFilter: 'blur(10px)'
            }}>
              <Sparkles size={18} color="#f38f95" />
              <span style={{ color: 'white', fontWeight: '500', fontSize: '0.9rem' }}>
                Active Subscription:
              </span>
              <span style={{ color: '#66c4e1', fontWeight: '600', fontSize: '0.9rem', textTransform: 'capitalize' }}>
                {userPlan} Plan
              </span>
            </div>
          )}

          {/* Tool Section */}
          <ToolSection
            freeCredits={freeCredits}
            setFreeCredits={setFreeCredits}
            toolState={toolState}
            setToolState={setToolState}
            session={session}
          />
        </div>
      </div>
    </>
  );
}
