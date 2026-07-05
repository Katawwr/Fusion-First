import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Loader, AlertTriangle, Zap, Shield, Sparkles } from 'lucide-react';
import ResultsPanel from '../components/tool/ResultsPanel';
import FixesPanel from '../components/tool/FixesPanel';
import { fetchScanDetail } from '../lib/api';
import { useAuth } from '../hooks';

const tabs = [
  { id: 'setup', label: 'Setup', icon: Zap },
  { id: 'results', label: 'Results', icon: Shield },
  { id: 'fixes', label: 'Fixes', icon: Sparkles },
];

export default function ScanDetail() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const { session, isAuthenticated } = useAuth();
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('results');

  useEffect(() => {
    if (!isAuthenticated || !session?.access_token || !scanId) return;
    loadScan();
  }, [isAuthenticated, session?.access_token, scanId]);

  const loadScan = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchScanDetail(session.access_token, scanId);
      setScan(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div style={{ maxWidth: '600px', margin: '0 auto', padding: '4rem 1rem', textAlign: 'center' }}>
        <p style={{ color: 'white' }}>Sign in to view scan results.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem 0' }}>
        <Loader size={32} color="#66c4e1" style={{ animation: 'spin 1s linear infinite' }} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ maxWidth: '600px', margin: '0 auto', padding: '4rem 1rem', textAlign: 'center' }}>
        <AlertTriangle size={48} color="#ef4444" style={{ margin: '0 auto 1rem' }} />
        <h2 style={{ color: '#ef4444', marginBottom: '0.75rem' }}>{error}</h2>
        <Link to="/dashboard" style={{ color: '#66c4e1', textDecoration: 'underline' }}>
          Back to Dashboard
        </Link>
      </div>
    );
  }

  if (!scan) return null;

  const date = new Date(scan.created_at).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });

  // Build results object matching what ResultsPanel/FixesPanel expect
  const resultsData = {
    summary: scan.summary,
    results: scan.results,
    fixes: scan.fixes,
    preventive_recommendations: scan.preventive_recommendations,
  };

  return (
    <div style={{
      maxWidth: '1200px',
      margin: '0 auto',
      padding: 'clamp(2rem, 4vw, 4rem) 1rem',
    }}>
      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <button
          onClick={() => navigate('/dashboard')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            background: 'none',
            border: 'none',
            color: '#66c4e1',
            fontSize: '0.875rem',
            cursor: 'pointer',
            padding: 0,
            marginBottom: '1rem',
          }}
        >
          <ArrowLeft size={16} />
          Back to Dashboard
        </button>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <h1 style={{
              color: 'white',
              fontSize: 'clamp(1.25rem, 3vw, 1.5rem)',
              fontWeight: 'bold',
              margin: '0 0 0.5rem 0',
              fontFamily: 'ui-monospace, monospace',
              wordBreak: 'break-all',
            }}>
              {scan.system_prompt_preview || 'Scan Result'}
            </h1>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.875rem', margin: 0 }}>
              {date} &middot; {scan.total_issues} issue{scan.total_issues !== 1 ? 's' : ''} found
            </p>
          </div>

        </div>
      </div>

      {/* Tab Navigation */}
      <nav style={{
        display: 'flex',
        justifyContent: 'center',
        gap: 'clamp(0.5rem, 2vw, 1rem)',
        marginBottom: '2rem',
      }}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          const isDisabled = tab.id === 'fixes' && !resultsData.fixes;
          return (
            <button
              key={tab.id}
              onClick={() => !isDisabled && setActiveTab(tab.id)}
              disabled={isDisabled}
              style={{
                padding: 'clamp(0.5rem, 2vw, 0.75rem) clamp(0.75rem, 3vw, 1.5rem)',
                fontWeight: '600',
                fontSize: 'clamp(0.875rem, 2vw, 1rem)',
                background: isActive ? 'rgba(243, 143, 149, 0.2)' : 'transparent',
                border: isActive ? '1px solid #f38f95' : '1px solid rgba(255,255,255,0.2)',
                borderRadius: '0.5rem',
                color: isActive ? '#f38f95' : isDisabled ? 'rgba(255,255,255,0.3)' : 'white',
                cursor: isDisabled ? 'not-allowed' : 'pointer',
                opacity: isDisabled ? 0.5 : 1,
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                whiteSpace: 'nowrap',
              }}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Tab Content */}
      <div style={{ minHeight: '400px' }}>
        {activeTab === 'setup' && (
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
            <h3 style={{ fontSize: 'clamp(1rem, 2vw, 1.25rem)', fontWeight: 'bold', color: 'white', marginBottom: '1rem' }}>
              System Prompt
            </h3>
            <pre style={{
              background: 'rgba(80, 77, 154, 0.5)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '0.5rem',
              padding: '1rem',
              fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)',
              color: 'white',
              whiteSpace: 'pre-wrap',
              fontFamily: 'ui-monospace, monospace',
              margin: 0,
              wordBreak: 'break-word',
              lineHeight: '1.6',
              maxHeight: '500px',
              overflowY: 'auto'
            }}>
              {scan.system_prompt || scan.system_prompt_preview}
            </pre>
          </div>
        )}
        {activeTab === 'results' && (
          <ResultsPanel results={resultsData} testing={false} />
        )}
        {activeTab === 'fixes' && (
          <FixesPanel
            fixes={resultsData.fixes}
            preventive_recommendations={resultsData.preventive_recommendations}
          />
        )}
      </div>
    </div>
  );
}
