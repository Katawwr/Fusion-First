import React from 'react';
import { Link } from 'react-router-dom';

export default function Footer() {
  return (
    <footer style={{
      borderTop: '1px solid rgba(255,255,255,0.1)',
      background: 'rgba(0,0,0,0.3)',
      backdropFilter: 'blur(10px)',
      marginTop: 'auto'
    }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: 'clamp(1rem, 2vw, 1.5rem)', textAlign: 'center' }}>
        <p style={{ color: 'white', fontSize: 'clamp(0.875rem, 2vw, 1rem)' }}>
          <span style={{ color: '#66c4e1', fontWeight: '600' }}>Fusion First</span> • Automated LLM Testing
        </p>
        <div style={{
          marginTop: '0.75rem',
          display: 'flex',
          gap: '1rem',
          justifyContent: 'center',
          alignItems: 'center',
          flexWrap: 'wrap',
          fontSize: 'clamp(0.65rem, 1.25vw, 0.75rem)'
        }}>
          <Link
            to="/privacy"
            style={{ color: '#66c4e1', textDecoration: 'underline', cursor: 'pointer' }}
          >
            Privacy Policy & Terms of Service
          </Link>
          <span style={{ color: 'rgba(255,255,255,0.5)' }}>
            © 2026 Fusion First
          </span>
        </div>
      </div>
    </footer>
  );
}
