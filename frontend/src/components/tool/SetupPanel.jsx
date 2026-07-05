import React from 'react';
import { Play, Loader } from 'lucide-react';

export default function SetupPanel({
  systemPrompt,
  setSystemPrompt,
  onRunTest,
  testing,
  freeCredits,
}) {
  const handleRunTest = () => {
    if (!systemPrompt) {
      alert('Please enter a system prompt');
      return;
    }
    if (freeCredits === null || freeCredits <= 0) {
      // Redirect to pricing section
      window.location.href = '/#pricing-section';
      return;
    }
    onRunTest();
  };

  return (
    <div style={{ width: '100%' }}>
      <div
        style={{
          background: 'rgba(80, 77, 154, 0.25)',
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(102, 196, 225, 0.2)',
          borderRadius: '1rem',
          padding: 'clamp(1rem, 3vw, 2rem)',
          transition: 'border-color 0.2s ease'
        }}
        onMouseEnter={(e) => e.currentTarget.style.borderColor = '#66c4e1'}
        onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)'}
      >
        <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
          <h2 style={{
            fontSize: 'clamp(1.5rem, 4vw, 1.875rem)',
            fontWeight: 'bold',
            marginBottom: '0.5rem',
            color: 'white'
          }}>
            Configure Test
          </h2>
          <p style={{ color: 'white', fontSize: 'clamp(0.875rem, 2vw, 1rem)' }}>
            Recommended for usage on long complex instructions for best results.
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* System Prompt */}
          <div>
            <label style={{
              display: 'block',
              fontSize: 'clamp(0.75rem, 2vw, 0.875rem)',
              fontWeight: '600',
              marginBottom: '0.5rem',
              color: '#66c4e1'
            }}>
              System Prompt
            </label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="You are a helpful customer service assistant..."
              rows={12}
              style={{
                width: '100%',
                padding: '0.75rem',
                background: 'rgba(80, 77, 154, 0.4)',
                border: '1px solid rgba(102, 196, 225, 0.3)',
                borderRadius: '0.5rem',
                color: 'white',
                fontFamily: 'monospace',
                fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)',
                resize: 'vertical',
                outline: 'none'
              }}
            />
          </div>

          {/* Run Test Button */}
          <button
            onClick={handleRunTest}
            disabled={!systemPrompt || testing || freeCredits === null || freeCredits <= 0}
            style={{
              width: '100%',
              padding: 'clamp(0.875rem, 2vw, 1rem)',
              background: freeCredits > 0 && !testing && systemPrompt ? 'linear-gradient(to right, #f38f95, #db418b)' : 'rgba(80, 77, 154, 0.3)',
              border: 'none',
              borderRadius: '0.5rem',
              color: freeCredits > 0 && !testing && systemPrompt ? 'white' : 'rgba(255,255,255,0.5)',
              fontWeight: 'bold',
              fontSize: 'clamp(1rem, 2.5vw, 1.125rem)',
              cursor: freeCredits > 0 && !testing && systemPrompt ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.75rem',
              transition: 'transform 0.2s ease'
            }}
            onMouseEnter={(e) => {
              if (freeCredits > 0 && !testing && systemPrompt) {
                e.currentTarget.style.transform = 'translateY(-2px)';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            {testing ? (
              <>
                <Loader size={24} style={{ animation: 'spin 1s linear infinite' }} />
                Running Tests...
              </>
            ) : freeCredits === null ? (
              <>
                <Loader size={24} style={{ animation: 'spin 1s linear infinite' }} />
                Loading...
              </>
            ) : freeCredits <= 0 ? (
              <>
                Get Credits
              </>
            ) : (
              <>
                <Play size={24} />
                Run Test
              </>
            )}
          </button>

          {/* Info Box */}
          <div
            style={{
              background: 'linear-gradient(to right, rgba(102, 196, 225, 0.15), rgba(243, 143, 149, 0.15))',
              border: '1px solid rgba(102, 196, 225, 0.4)',
              borderRadius: '0.5rem',
              padding: '1rem',
              transition: 'border-color 0.2s ease'
            }}
            onMouseEnter={(e) => e.currentTarget.style.borderColor = '#66c4e1'}
            onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.4)'}
          >
            <div style={{ fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)' }}>
              <p style={{ fontWeight: '600', marginBottom: '0.5rem', color: '#66c4e1' }}>Quality Testing Includes:</p>
              <p style={{ color: 'white', marginBottom: '0.5rem' }}>
                Comprehensive quality tests detecting real-world issues that affect LLM output quality and reliability.
              </p>
              <ul className="quality-testing-list" style={{
                color: 'white',
                lineHeight: '1.5',
                paddingLeft: 'clamp(1rem, 3vw, 1.25rem)',
                margin: 0,
                listStyleType: 'disc',
                listStylePosition: 'outside'
              }}>
                <li>Hallucination Detection - Confirming non-existent features/facts</li>
                <li>Ambiguity Handling - Proceeding without clarifying vague inputs</li>
                <li>Scope Creep - Adding unrequested features or suggestions</li>
                <li>Boundary Violations - Ignoring explicit constraints</li>
                <li>Instruction Following - Violating tone, format, or content rules</li>
                <li>Context Retention - Losing key details in long prompts</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
