import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, Zap, AlertTriangle, CheckCircle } from 'lucide-react';

export default function Hero() {
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef(null);
  const navigate = useNavigate();

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

  const goToTest = () => {
    navigate('/scan');
  };

  const scrollToPricing = () => {
    const pricingSection = document.getElementById('pricing-section');
    if (pricingSection) {
      pricingSection.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const features = [
    { icon: AlertTriangle, text: 'Catch prompt injection & hijacks (LLM01)' },
    { icon: Zap, text: 'Stop runaway actions & excessive agency (LLM06)' },
    { icon: Shield, text: 'Block data exfiltration (LLM02)' },
    { icon: CheckCircle, text: 'Prevent system-prompt & secret leakage (LLM07)' },
  ];

  return (
    <section
      ref={sectionRef}
      style={{
        position: 'relative',
        padding: 'clamp(3rem, 8vw, 5rem) 0',
        overflow: 'hidden',
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
        transition: 'opacity 0.6s ease-out, transform 0.6s ease-out'
      }}
    >
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 1rem' }}>
        <div style={{ textAlign: 'center' }}>
          {/* Badge */}
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.5rem 1rem',
            borderRadius: '9999px',
            background: 'var(--surface)',
            border: '1px solid var(--border-strong)',
            marginBottom: '2rem'
          }}>
            <span style={{ color: 'var(--accent-ink)', fontSize: '0.875rem', fontWeight: '500' }}>Free demo scan</span>
            <span style={{ color: 'var(--text)', fontSize: '0.875rem' }}>No signup required</span>
          </div>

          {/* Main heading */}
          <h1 style={{
            fontSize: 'clamp(2rem, 6vw, 3.5rem)',
            fontWeight: 'bold',
            color: 'var(--text)',
            marginBottom: '1.5rem',
            lineHeight: 1.2
          }}>
            Ship AI agents you can{' '}
            <span style={{
              background: 'linear-gradient(to right, #66c4e1, #f38f95)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}>
              prove
            </span>
            {' '}are safe
          </h1>

          {/* Subheading */}
          <p style={{
            fontSize: 'clamp(1rem, 2.5vw, 1.25rem)',
            color: 'var(--text)',
            maxWidth: '800px',
            margin: '0 auto 2.5rem',
            lineHeight: 1.6
          }}>
            Paste your bot's system prompt. Fusion runs an OWASP-mapped attack suite, grades it
            baseline vs hardened, and hands you a one-click fix — every number backed by a
            confidence interval, not a vibe.
          </p>

          {/* CTA buttons */}
          <div style={{
            display: 'flex',
            flexDirection: 'row',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '1rem',
            marginBottom: '3rem'
          }}>
            <button
              onClick={goToTest}
              style={{
                padding: '0.875rem 2rem',
                background: 'linear-gradient(to right, #f38f95, #db418b)',
                border: 'none',
                borderRadius: '0.5rem',
                color: '#fff',
                fontWeight: 'bold',
                fontSize: '1rem',
                cursor: 'pointer',
                transition: 'transform 0.2s ease'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-3px)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              Scan your bot free
            </button>
            <button
              onClick={scrollToPricing}
              style={{
                padding: '0.875rem 2rem',
                background: 'transparent',
                border: '2px solid #66c4e1',
                borderRadius: '0.5rem',
                color: 'var(--accent-ink)',
                fontWeight: 'bold',
                fontSize: '1rem',
                cursor: 'pointer',
                transition: 'transform 0.2s ease, background 0.2s ease, color 0.2s ease'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-3px)';
                e.currentTarget.style.background = 'rgba(102, 196, 225, 0.15)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.background = 'transparent';
              }}
            >
              View Pricing
            </button>
          </div>

          {/* Feature highlights */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '1rem',
            maxWidth: '900px',
            margin: '0 auto'
          }}>
            {features.map((feature, index) => {
              const Icon = feature.icon;
              return (
                <div
                  key={index}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '1rem',
                    borderRadius: '0.75rem',
                    background: 'var(--surface)',
                    border: '1px solid var(--border)',
                    transition: 'border-color 0.2s ease, transform 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#66c4e1';
                    e.currentTarget.style.transform = 'translateY(-2px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border)';
                    e.currentTarget.style.transform = 'translateY(0)';
                  }}
                >
                  <Icon size={20} color="#66c4e1" style={{ flexShrink: 0 }} />
                  <span style={{ fontSize: '0.875rem', color: 'var(--text)', textAlign: 'left' }}>{feature.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
