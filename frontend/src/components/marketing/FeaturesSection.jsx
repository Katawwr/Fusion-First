import React, { useEffect, useRef, useState } from 'react';
import { Cpu, Target, Layers, GitBranch, BarChart3, RefreshCw } from 'lucide-react';

const features = [
  {
    icon: Cpu,
    title: 'Dynamic Prompt Generation',
    description: 'Our AI analyzes your system prompt to generate 20 custom attack vectors tailored specifically to your use case, not generic tests.'
  },
  {
    icon: Target,
    title: 'Multi-Dimensional Analysis',
    description: 'Each test probes different failure modes: factual accuracy, boundary adherence, context retention, and instruction following simultaneously.'
  },
  {
    icon: Layers,
    title: 'Severity Classification',
    description: 'Issues are automatically categorized by severity (critical, high, medium, low) so you can prioritize fixes that matter most.'
  },
  {
    icon: GitBranch,
    title: 'Root Cause Identification',
    description: 'Beyond detecting issues, we identify the specific prompt patterns causing failures so you know exactly what to fix.'
  },
  {
    icon: BarChart3,
    title: 'Quality Scoring',
    description: 'Get an overall quality score with breakdown by category, enabling you to track improvements across iterations.'
  },
  {
    icon: RefreshCw,
    title: 'AI-Generated Fixes',
    description: 'Receive specific, actionable prompt modifications for each identified issue, ready to copy and implement.'
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
            color: 'white',
            marginBottom: '1rem'
          }}>
            How It Works
          </h2>
          <p style={{
            fontSize: '1.125rem',
            color: 'white',
            maxWidth: '700px',
            margin: '0 auto',
            lineHeight: 1.6
          }}>
            Our quality testing engine goes beyond surface-level checks to find the issues that actually affect your users.
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
                  background: 'rgba(80, 77, 154, 0.25)',
                  border: '1px solid rgba(102, 196, 225, 0.2)',
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
                  e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)';
                }}
              >
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '0.75rem',
                  background: 'linear-gradient(135deg, rgba(102, 196, 225, 0.2), rgba(243, 143, 149, 0.2))',
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
                  color: 'white',
                  marginBottom: '0.5rem'
                }}>
                  {feature.title}
                </h3>
                <p style={{
                  color: 'rgba(255, 255, 255, 0.8)',
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
