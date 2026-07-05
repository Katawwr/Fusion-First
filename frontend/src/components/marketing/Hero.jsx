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
    navigate('/test');
  };

  const scrollToPricing = () => {
    const pricingSection = document.getElementById('pricing-section');
    if (pricingSection) {
      pricingSection.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const features = [
    { icon: AlertTriangle, text: 'Detect hallucinations & false claims' },
    { icon: Shield, text: 'Test boundary violations' },
    { icon: Zap, text: 'AI-powered fix recommendations' },
    { icon: CheckCircle, text: '20+ quality test categories' },
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
            background: 'rgba(80, 77, 154, 0.25)',
            border: '1px solid rgba(102, 196, 225, 0.3)',
            marginBottom: '2rem'
          }}>
            <span style={{ color: '#66c4e1', fontSize: '0.875rem', fontWeight: '500' }}>2 Free Scans</span>
            <span style={{ color: 'white', fontSize: '0.875rem' }}>No signup required</span>
          </div>

          {/* Main heading */}
          <h1 style={{
            fontSize: 'clamp(2rem, 6vw, 3.5rem)',
            fontWeight: 'bold',
            color: 'white',
            marginBottom: '1.5rem',
            lineHeight: 1.2
          }}>
            Test Your LLM for{' '}
            <span style={{
              background: 'linear-gradient(to right, #66c4e1, #f38f95)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}>
              Quality Issues
            </span>
            <br />Before They Reach Production
          </h1>

          {/* Subheading */}
          <p style={{
            fontSize: 'clamp(1rem, 2.5vw, 1.25rem)',
            color: 'white',
            maxWidth: '800px',
            margin: '0 auto 2.5rem',
            lineHeight: 1.6
          }}>
            Automatically detect hallucinations, boundary violations, and instruction failures
            in your LLM system prompts. Get AI-powered recommendations to fix issues in minutes.
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
                color: 'white',
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
              Start Testing
            </button>
            <button
              onClick={scrollToPricing}
              style={{
                padding: '0.875rem 2rem',
                background: 'transparent',
                border: '2px solid #66c4e1',
                borderRadius: '0.5rem',
                color: '#66c4e1',
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
                    background: 'rgba(80, 77, 154, 0.25)',
                    border: '1px solid rgba(102, 196, 225, 0.2)',
                    transition: 'border-color 0.2s ease, transform 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#66c4e1';
                    e.currentTarget.style.transform = 'translateY(-2px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)';
                    e.currentTarget.style.transform = 'translateY(0)';
                  }}
                >
                  <Icon size={20} color="#66c4e1" style={{ flexShrink: 0 }} />
                  <span style={{ fontSize: '0.875rem', color: 'white', textAlign: 'left' }}>{feature.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
