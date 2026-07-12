import React, { useEffect, useRef, useState } from 'react';
import { Cpu, Target, Layers, GitBranch, BarChart3, RefreshCw } from 'lucide-react';

const features = [
  {
    icon: Target,
    title: 'OWASP-mapped attack suite',
    description: 'Every check maps to the OWASP Top 10 for LLMs (2025) and Agentic AI (2026) — prompt injection, excessive agency, data exfiltration, secret leakage. You test the risks the industry actually tracks, not a made-up list.'
  },
  {
    icon: GitBranch,
    title: 'Baseline vs hardened, side by side',
    description: 'We run the same attacks against your prompt as-is and against a hardened version, then report the exact lift — an apples-to-apples before/after, not a one-shot score.'
  },
  {
    icon: BarChart3,
    title: 'Numbers you can defend',
    description: 'Every result carries a 95% confidence interval and a PROVEN / PRELIMINARY / INCONCLUSIVE badge. Fusion refuses to claim an improvement the evidence cannot back.'
  },
  {
    icon: Cpu,
    title: 'A calibrated AI examiner',
    description: 'An AI judge scores each response against a written rubric — and we measure the judge itself against known-answer cases, so you know exactly how far to trust the grade.'
  },
  {
    icon: RefreshCw,
    title: 'One-click fix, two layers',
    description: 'Get a hardened system prompt plus a runtime guardrail SDK that blocks leaked secrets and unauthorized actions even when the model slips. Copy, paste, done.'
  },
  {
    icon: Layers,
    title: 'A report card anyone can read',
    description: 'Every OWASP term and statistic is translated into a plain question a founder can answer — with the real term one hover away. Share the card or export it as HTML.'
  }
];

export default function FeaturesSection() {
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.1 }
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={sectionRef}
      style={{
        padding: 'clamp(3rem, 6vw, 5rem) 0',
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
        transition: 'opacity 0.6s ease-out, transform 0.6s ease-out'
      }}
    >
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 1rem' }}>
        {/* Section header */}
        <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
          <h2 style={{
            fontSize: 'clamp(1.75rem, 4vw, 2.5rem)',
            fontWeight: 'bold',
            color: 'var(--text)',
            marginBottom: '1rem'
          }}>
            Proof, not vibes
          </h2>
          <p style={{
            fontSize: '1.125rem',
            color: 'var(--text)',
            maxWidth: '700px',
            margin: '0 auto',
            lineHeight: 1.6
          }}>
            Anyone can say your bot is "safer." Fusion measures it — against a real threat taxonomy,
            with statistics that admit their own uncertainty.
          </p>
        </div>

        {/* Features grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '1.5rem'
        }}>
          {features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <div
                key={index}
                className="feature-card"
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: '1rem',
                  padding: '1.5rem',
                  backdropFilter: 'blur(10px)',
                  opacity: isVisible ? 1 : 0,
                  transform: isVisible ? 'translateY(0)' : 'translateY(20px)',
                  transition: `opacity 0.5s ease-out ${index * 0.1}s, transform 0.5s ease-out ${index * 0.1}s, border-color 0.3s ease`,
                  cursor: 'default'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#66c4e1';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)';
                }}
              >
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '0.75rem',
                  background: 'linear-gradient(135deg, var(--border), rgba(243, 143, 149, 0.2))',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '1rem'
                }}>
                  <Icon size={24} color="#66c4e1" />
                </div>
                <h3 style={{
                  fontSize: '1.125rem',
                  fontWeight: '600',
                  color: 'var(--text)',
                  marginBottom: '0.5rem'
                }}>
                  {feature.title}
                </h3>
                <p style={{
                  color: 'var(--muted)',
                  fontSize: '0.9rem',
                  lineHeight: 1.6
                }}>
                  {feature.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
