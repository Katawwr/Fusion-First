import React, { useState } from 'react';
import { Sparkles, Copy, Check } from 'lucide-react';

export default function FixesPanel({ fixes, preventive_recommendations }) {
  const [copiedFixes, setCopiedFixes] = useState(false);
  const [copiedPreventive, setCopiedPreventive] = useState(false);

  const handleCopy = (text, setterFn) => {
    navigator.clipboard.writeText(text);
    setterFn(true);
    setTimeout(() => setterFn(false), 2000);
  };
  if (!fixes) {
    return (
      <div
        style={{
          background: 'rgba(80, 77, 154, 0.25)',
          border: '1px solid rgba(102, 196, 225, 0.2)',
          borderRadius: '1rem',
          padding: '3rem',
          textAlign: 'center',
          transition: 'border-color 0.2s ease'
        }}
        onMouseEnter={(e) => e.currentTarget.style.borderColor = '#66c4e1'}
        onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)'}
      >
        <Sparkles size={48} color="#66c4e1" style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
        <p style={{ color: 'white' }}>
          No fixes available. Run a test to get AI-powered recommendations.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div
        style={{
          background: 'rgba(80, 77, 154, 0.25)',
          border: '1px solid rgba(102, 196, 225, 0.2)',
          borderRadius: '1rem',
          padding: 'clamp(1rem, 3vw, 1.5rem)',
          transition: 'border-color 0.2s ease'
        }}
        onMouseEnter={(e) => e.currentTarget.style.borderColor = '#66c4e1'}
        onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)'}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <h3 style={{ fontSize: 'clamp(1rem, 2vw, 1.25rem)', fontWeight: 'bold', color: 'white', marginBottom: '0.5rem' }}>
              System Prompt Additions
            </h3>
            <p style={{ color: 'white', fontSize: '0.875rem' }}>
              You may want to create a section for specific use-cases to incorporate these into your instructions.
            </p>
          </div>
          <button
            onClick={(e) => {
              handleCopy(fixes, setCopiedFixes);
              e.currentTarget.style.transform = 'scale(0.95)';
              setTimeout(() => {
                e.currentTarget.style.transform = 'scale(1)';
              }, 100);
            }}
            style={{
              padding: '0.5rem',
              background: 'rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.3)',
              borderRadius: '0.375rem',
              color: 'white',
              cursor: 'pointer',
              flexShrink: 0,
              transition: 'transform 0.1s ease',
            }}
          >
            {copiedFixes ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </div>
      </div>

      {/* Fixes Content */}
      <div style={{
        background: 'rgba(80, 77, 154, 0.5)',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: '0.5rem',
        padding: '1rem',
        maxHeight: '500px',
        overflowY: 'auto'
      }}>
        <pre style={{
          fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)',
          color: 'white',
          whiteSpace: 'pre-wrap',
          fontFamily: 'ui-monospace, monospace',
          margin: 0,
          wordBreak: 'break-word',
          lineHeight: '1.6'
        }}>
          {fixes}
        </pre>
      </div>

      {/* Preventive Recommendations Section */}
      {preventive_recommendations && (
        <>
          {/* Preventive Recommendations Header */}
          <div
            style={{
              background: 'rgba(80, 77, 154, 0.25)',
              border: '1px solid rgba(102, 196, 225, 0.2)',
              borderRadius: '1rem',
              padding: 'clamp(1rem, 3vw, 1.5rem)',
              transition: 'border-color 0.2s ease'
            }}
            onMouseEnter={(e) => e.currentTarget.style.borderColor = '#66c4e1'}
            onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)'}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <h3 style={{ fontSize: 'clamp(1rem, 2vw, 1.25rem)', fontWeight: 'bold', color: 'white', marginBottom: '0.5rem' }}>
                  Preventive Recommendations
                </h3>
                <p style={{ color: 'white', fontSize: '0.875rem' }}>
                  These recommendations address near-misses and potential vulnerabilities to strengthen your system.
                </p>
              </div>
              <button
                onClick={(e) => {
                  handleCopy(preventive_recommendations, setCopiedPreventive);
                  e.currentTarget.style.transform = 'scale(0.95)';
                  setTimeout(() => {
                    e.currentTarget.style.transform = 'scale(1)';
                  }, 100);
                }}
                style={{
                  padding: '0.5rem',
                  background: 'rgba(255,255,255,0.1)',
                  border: '1px solid rgba(255,255,255,0.3)',
                  borderRadius: '0.375rem',
                  color: 'white',
                  cursor: 'pointer',
                  flexShrink: 0,
                  transition: 'transform 0.1s ease',
                }}
              >
                {copiedPreventive ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
          </div>

          {/* Preventive Recommendations Content */}
          <div style={{
            background: 'rgba(80, 77, 154, 0.5)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '0.5rem',
            padding: '1rem',
            maxHeight: '500px',
            overflowY: 'auto'
          }}>
            <pre style={{
              fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)',
              color: 'white',
              whiteSpace: 'pre-wrap',
              fontFamily: 'ui-monospace, monospace',
              margin: 0,
              wordBreak: 'break-word',
              lineHeight: '1.6'
            }}>
              {preventive_recommendations}
            </pre>
          </div>
        </>
      )}
    </div>
  );
}
