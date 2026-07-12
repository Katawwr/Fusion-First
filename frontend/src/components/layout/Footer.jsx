import React from 'react';
import { Link } from 'react-router-dom';

export default function Footer() {
  return (
    <footer style={{
      borderTop: '1px solid var(--border)',
      background: 'var(--bg-elev)',
      backdropFilter: 'blur(10px)',
      marginTop: 'auto'
    }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: 'clamp(1rem, 2vw, 1.5rem)', textAlign: 'center' }}>
        <p style={{ color: 'var(--text)', fontSize: 'clamp(0.875rem, 2vw, 1rem)' }}>
          <span style={{ color: 'var(--accent-ink)', fontWeight: '600' }}>Fusion First</span> • Test, prove &amp; harden your AI agents
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
            style={{ color: 'var(--accent-ink)', textDecoration: 'underline', cursor: 'pointer' }}
          >
            Privacy Policy & Terms of Service
          </Link>
          <span style={{ color: 'var(--subtle)' }}>
            © 2026 Fusion First
          </span>
        </div>
      </div>
    </footer>
  );
}
