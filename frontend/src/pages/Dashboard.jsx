import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { History, AlertTriangle, ArrowRight, Loader, RefreshCw, Zap, Key, Plus, Trash2, Copy, Check, Code } from 'lucide-react';
import { fetchScanHistory, createApiKey, listApiKeys, revokeApiKey } from '../lib/api';
import { API_URL } from '../lib/constants';
import { useAuth } from '../hooks';
import { SignInModal } from '../components/auth';

const severityBadgeStyles = {
  CRITICAL: { bg: 'rgba(239, 68, 68, 0.2)', border: 'rgba(239, 68, 68, 0.5)', text: '#ef4444' },
  HIGH: { bg: 'rgba(251, 146, 60, 0.2)', border: 'rgba(251, 146, 60, 0.5)', text: '#fb923c' },
  MEDIUM: { bg: 'rgba(250, 204, 21, 0.2)', border: 'rgba(250, 204, 21, 0.5)', text: '#facc15' },
  LOW: { bg: 'rgba(34, 197, 94, 0.15)', border: 'rgba(34, 197, 94, 0.4)', text: '#22c55e' },
};

function SeverityMini({ label, count }) {
  if (!count) return null;
  const style = severityBadgeStyles[label] || severityBadgeStyles.LOW;
  return (
    <span style={{
      padding: '0.15rem 0.5rem',
      borderRadius: '0.375rem',
      fontSize: '0.7rem',
      fontWeight: '600',
      background: style.bg,
      border: `1px solid ${style.border}`,
      color: style.text,
    }}>
      {count} {label}
    </span>
  );
}

function ScanCard({ scan }) {
  const navigate = useNavigate();
  const severity = scan.summary?.by_severity || {};
  const date = new Date(scan.created_at).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });

  return (
    <div
      onClick={() => navigate(`/dashboard/scan/${scan.id}`)}
      style={{
        background: 'rgba(80, 77, 154, 0.25)',
        border: '1px solid rgba(102, 196, 225, 0.2)',
        borderRadius: '0.75rem',
        padding: 'clamp(1rem, 2vw, 1.25rem)',
        cursor: 'pointer',
        transition: 'border-color 0.2s ease, transform 0.2s ease',
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{
            color: 'white',
            fontSize: 'clamp(0.8rem, 2vw, 1rem)',
            fontWeight: '500',
            margin: '0 0 0.5rem 0',
            fontFamily: 'ui-monospace, monospace',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {scan.system_prompt_preview || 'Untitled scan'}
          </p>
          <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', margin: 0 }}>
            {date}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          {scan.total_issues > 0 ? (
            <>
              <SeverityMini label="CRITICAL" count={severity.CRITICAL} />
              <SeverityMini label="HIGH" count={severity.HIGH} />
              <SeverityMini label="MEDIUM" count={severity.MEDIUM} />
              <SeverityMini label="LOW" count={severity.LOW} />
            </>
          ) : (
            <span style={{
              padding: '0.15rem 0.5rem',
              borderRadius: '0.375rem',
              fontSize: '0.7rem',
              fontWeight: '600',
              background: 'rgba(255, 255, 255, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.3)',
              color: '#ffffff',
            }}>
              NONE
            </span>
          )}
          <ArrowRight size={16} color="rgba(255,255,255,0.4)" />
        </div>
      </div>
    </div>
  );
}

// ─── API Keys Section ────────────────────────────────────────────────

function ApiKeysSection({ session }) {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [revealedKey, setRevealedKey] = useState(null); // full key shown once after creation
  const [copied, setCopied] = useState(false);
  const [showSnippets, setShowSnippets] = useState(false);

  useEffect(() => {
    loadKeys();
  }, [session?.access_token]);

  const loadKeys = async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const data = await listApiKeys(session.access_token);
      setKeys(data.keys || []);
    } catch (err) {
      console.error('Failed to load API keys:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    setCreating(true);
    try {
      const data = await createApiKey(session.access_token, newKeyName.trim());
      setRevealedKey(data.key);
      setNewKeyName('');
      await loadKeys();
    } catch (err) {
      alert(`Failed to create key: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (keyId) => {
    if (!confirm('Are you sure you want to revoke this API key? This cannot be undone.')) return;
    try {
      await revokeApiKey(session.access_token, keyId);
      await loadKeys();
    } catch (err) {
      alert(`Failed to revoke key: ${err.message}`);
    }
  };

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const curlSnippet = `curl -X POST ${API_URL}/api/v1/scan \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"system_prompt": "You are a helpful assistant..."}'`;

  const githubActionsSnippet = `- name: Run Fusion First Scan
  run: |
    RESULT=$(curl -s -X POST ${API_URL}/api/v1/scan \\
      -H "X-API-Key: \${{ secrets.FUSION_API_KEY }}" \\
      -H "Content-Type: application/json" \\
      -d '{"system_prompt": "'"$(cat prompt.txt)"'"}')
    CRITICAL=$(echo "$RESULT" | jq '.summary.by_severity.CRITICAL')
    if [ "$CRITICAL" -gt 0 ]; then
      echo "CRITICAL issues found!" && exit 1
    fi`;

  const pythonSnippet = `import requests

response = requests.post(
    "${API_URL}/api/v1/scan",
    headers={"X-API-Key": "YOUR_API_KEY", "Content-Type": "application/json"},
    json={"system_prompt": "You are a helpful assistant..."},
)
result = response.json()
print(f"Issues found: {result['summary']['issues_found']}")`;

  return (
    <div style={{ marginTop: '3rem' }}>
      <h2 style={{ color: 'white', fontSize: 'clamp(1.25rem, 3vw, 1.5rem)', fontWeight: 'bold', marginBottom: '1rem' }}>
        API Keys
      </h2>
      <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
        Use API keys to run scans programmatically from CI/CD pipelines or scripts.
      </p>

      {/* Revealed key banner */}
      {revealedKey && (
        <div style={{
          background: 'rgba(34, 197, 94, 0.1)',
          border: '1px solid rgba(34, 197, 94, 0.4)',
          borderRadius: '0.75rem',
          padding: '1rem',
          marginBottom: '1.5rem',
        }}>
          <p style={{ color: 'white', fontWeight: '600', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
            API key created! Copy it now - you won't see it again.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <code style={{
              flex: 1,
              background: 'rgba(0,0,0,0.3)',
              padding: '0.5rem 0.75rem',
              borderRadius: '0.375rem',
              fontSize: '0.8rem',
              color: 'white',
              fontFamily: 'ui-monospace, monospace',
              wordBreak: 'break-all',
            }}>
              {revealedKey}
            </code>
            <button
              onClick={(e) => {
                handleCopy(revealedKey);
                e.currentTarget.style.transform = 'scale(0.95)';
                setTimeout(() => {
                  e.currentTarget.style.transform = 'scale(1)';
                }, 100);
              }}
              style={{
                padding: '0.5rem',
                background: 'rgba(34, 197, 94, 0.2)',
                border: '1px solid rgba(34, 197, 94, 0.4)',
                borderRadius: '0.375rem',
                color: '#22c55e',
                cursor: 'pointer',
                flexShrink: 0,
                transition: 'transform 0.1s ease',
              }}
            >
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
          <button
            onClick={() => setRevealedKey(null)}
            style={{
              marginTop: '0.75rem',
              padding: '0.25rem 0.75rem',
              background: 'transparent',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '0.375rem',
              color: 'rgba(255,255,255,0.6)',
              fontSize: '0.75rem',
              cursor: 'pointer',
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Create key form */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <input
          type="text"
          value={newKeyName}
          onChange={(e) => setNewKeyName(e.target.value)}
          placeholder="Name key (e.g., 'Production Server')"
          maxLength={50}
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          style={{
            flex: 1,
            minWidth: 0,
            padding: '0.5rem 0.75rem',
            background: 'rgba(80, 77, 154, 0.4)',
            border: '1px solid rgba(102, 196, 225, 0.2)',
            borderRadius: '0.5rem',
            color: 'white',
            fontSize: '0.875rem',
            outline: 'none',
          }}
        />
        <button
          onClick={handleCreate}
          disabled={creating || !newKeyName.trim()}
          style={{
            padding: '0.5rem 1rem',
            background: 'linear-gradient(to right, #f38f95, #db418b)',
            border: 'none',
            borderRadius: '0.5rem',
            color: 'white',
            fontWeight: '600',
            fontSize: '0.875rem',
            cursor: creating || !newKeyName.trim() ? 'not-allowed' : 'pointer',
            opacity: creating || !newKeyName.trim() ? 0.5 : 1,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            whiteSpace: 'nowrap',
          }}
        >
          <Plus size={14} />
          {creating ? 'Creating...' : 'Create Key'}
        </button>
      </div>

      {/* Keys list */}
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem 0' }}>
          <Loader size={24} color="#66c4e1" style={{ animation: 'spin 1s linear infinite' }} />
        </div>
      ) : keys.length === 0 ? (
        <div style={{
          background: 'rgba(80, 77, 154, 0.25)',
          border: '1px solid rgba(102, 196, 225, 0.2)',
          borderRadius: '0.75rem',
          padding: '2rem',
          textAlign: 'center',
        }}>
          <Key size={32} color="#66c4e1" style={{ margin: '0 auto 0.75rem', opacity: 0.5 }} />
          <p style={{ color: 'white', fontWeight: '600', margin: 0, fontSize: '0.875rem' }}>
            No API keys yet
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {keys.map((k) => (
            <div
              key={k.id}
              style={{
                background: 'rgba(80, 77, 154, 0.25)',
                border: `1px solid ${k.is_active ? 'rgba(102, 196, 225, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`,
                borderRadius: '0.75rem',
                padding: '0.75rem 1rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '1rem',
                flexWrap: 'wrap',
                opacity: k.is_active ? 1 : 0.5,
                transition: 'border-color 0.2s ease, transform 0.2s ease',
              }}
              onMouseEnter={(e) => {
                if (k.is_active) {
                  e.currentTarget.style.borderColor = '#66c4e1';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }
              }}
              onMouseLeave={(e) => {
                if (k.is_active) {
                  e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)';
                  e.currentTarget.style.transform = 'translateY(0)';
                }
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: 0 }}>
                <Key size={14} color={k.is_active ? '#66c4e1' : '#ef4444'} />
                <div>
                  <p style={{ color: 'white', fontSize: '0.875rem', fontWeight: '500', margin: 0 }}>
                    {k.name}
                    {!k.is_active && <span style={{ color: '#ef4444', marginLeft: '0.5rem', fontSize: '0.75rem' }}>Revoked</span>}
                  </p>
                  <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.7rem', margin: 0, fontFamily: 'ui-monospace, monospace' }}>
                    {k.key_prefix}
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.7rem', whiteSpace: 'nowrap' }}>
                  {k.last_used_at ? `Used ${new Date(k.last_used_at).toLocaleDateString()}` : 'Never used'}
                </span>
                {k.is_active && (
                  <button
                    onClick={() => handleRevoke(k.id)}
                    style={{
                      padding: '0.35rem 0.75rem',
                      background: 'rgba(239, 68, 68, 0.1)',
                      border: '1px solid rgba(239, 68, 68, 0.3)',
                      borderRadius: '0.375rem',
                      color: '#ef4444',
                      fontSize: '0.75rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    <Trash2 size={12} />
                    Revoke
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Code snippets toggle */}
      <button
        onClick={() => setShowSnippets(!showSnippets)}
        style={{
          marginTop: '1.5rem',
          padding: '0.5rem 1rem',
          background: 'transparent',
          border: '1px solid rgba(255,255,255,0.2)',
          borderRadius: '0.5rem',
          color: 'white',
          fontSize: '0.875rem',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}
      >
        <Code size={14} />
        {showSnippets ? 'Hide' : 'Show'} Usage Examples
      </button>

      {showSnippets && (
        <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {[
            { label: 'curl', code: curlSnippet },
            { label: 'GitHub Actions', code: githubActionsSnippet },
            { label: 'Python', code: pythonSnippet },
          ].map(({ label, code }) => (
            <div key={label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                <span style={{ color: 'white', fontSize: '0.75rem', fontWeight: '600' }}>{label}</span>
                <button
                  onClick={(e) => {
                    handleCopy(code);
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
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    transition: 'transform 0.1s ease',
                  }}
                >
                  <Copy size={12} />
                </button>
              </div>
              <pre style={{
                background: 'rgba(0,0,0,0.3)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '0.5rem',
                padding: '0.75rem',
                fontSize: '0.7rem',
                color: 'white',
                fontFamily: 'ui-monospace, monospace',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                margin: 0,
                overflowX: 'auto',
              }}>
                {code}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main Dashboard Component ────────────────────────────────────────

export default function Dashboard({ setToolState }) {
  const { session, isAuthenticated, loading: authLoading, requestMagicLink, magicLinkSent, error: authError } = useAuth();
  const navigate = useNavigate();
  const [signInModalOpen, setSignInModalOpen] = useState(false);
  const [scans, setScans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isVisible, setIsVisible] = useState(false);
  const LIMIT = 20;

  useEffect(() => {
    // Small delay to ensure smooth fade-in on mount
    const timer = setTimeout(() => {
      setIsVisible(true);
    }, 50);

    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadScans();
  }, [isAuthenticated, session?.access_token]);

  const loadScans = async (newOffset = 0) => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchScanHistory(session.access_token, newOffset, LIMIT);
      if (newOffset === 0) {
        setScans(data.scans);
      } else {
        setScans(prev => [...prev, ...data.scans]);
      }
      setOffset(newOffset);
      setHasMore(data.scans.length === LIMIT);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <>
        <div style={{
          maxWidth: '600px',
          margin: '0 auto',
          padding: 'clamp(3rem, 6vw, 6rem) 1rem',
          textAlign: 'center',
        }}>
          <History size={48} color="#66c4e1" style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
          <h2 style={{ color: 'white', fontSize: 'clamp(1.25rem, 3vw, 1.5rem)', fontWeight: 'bold', marginBottom: '0.75rem' }}>
            Sign in to view your Dashboard
          </h2>
          <p style={{ color: 'rgba(255,255,255,0.7)', marginBottom: '1.5rem' }}>
            Your scan history and results are saved automatically when you're signed in.
          </p>
          <button
            onClick={() => setSignInModalOpen(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.75rem 1.5rem',
              background: 'linear-gradient(to right, #f38f95, #db418b)',
              border: 'none',
              borderRadius: '0.5rem',
              color: 'white',
              fontWeight: 'bold',
              cursor: 'pointer',
            }}
          >
            Sign In
          </button>
        </div>
        <SignInModal
          isOpen={signInModalOpen}
          onClose={() => setSignInModalOpen(false)}
          onRequestMagicLink={async (email, marketingOptIn) => { await requestMagicLink(email, marketingOptIn); }}
          loading={authLoading}
          magicLinkSent={magicLinkSent}
          error={authError}
          session={session}
        />
      </>
    );
  }

  return (
    <div
      style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: 'clamp(1.5rem, 4vw, 4rem) clamp(0.75rem, 3vw, 1rem)',
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
        transition: 'opacity 0.6s ease-out, transform 0.6s ease-out',
        overflowX: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ color: 'white', fontSize: 'clamp(1.5rem, 3vw, 2rem)', fontWeight: 'bold', margin: 0 }}>
            Dashboard
          </h1>
          <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 'clamp(0.75rem, 2vw, 0.875rem)', margin: '0.25rem 0 0 0' }}>
            Your scan history, results, and API keys
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => loadScans(0)}
            disabled={loading}
            style={{
              padding: '0.5rem 1rem',
              background: 'transparent',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '0.5rem',
              color: 'white',
              fontSize: '0.875rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <RefreshCw size={14} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
            Refresh
          </button>
          <button
            onClick={() => {
              if (setToolState) {
                setToolState({ systemPrompt: '', results: null, activeTab: 'setup' });
              }
              navigate('/test');
            }}
            style={{
              padding: '0.5rem 1rem',
              background: 'linear-gradient(to right, #f38f95, #db418b)',
              border: 'none',
              borderRadius: '0.5rem',
              color: 'white',
              fontWeight: '600',
              fontSize: '0.875rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <Zap size={14} />
            New Scan
          </button>
        </div>
      </div>

      {/* Scan History Section */}
      <h2 style={{ color: 'white', fontSize: 'clamp(1.25rem, 3vw, 1.5rem)', fontWeight: 'bold', marginBottom: '1rem' }}>
        Scan History
      </h2>

      {/* Error */}
      {error && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '0.75rem',
          padding: '1rem',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
        }}>
          <AlertTriangle size={18} color="#ef4444" />
          <p style={{ color: '#ef4444', margin: 0, fontSize: '0.875rem' }}>{error}</p>
        </div>
      )}

      {/* Loading */}
      {loading && scans.length === 0 && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem 0' }}>
          <Loader size={32} color="#66c4e1" style={{ animation: 'spin 1s linear infinite' }} />
        </div>
      )}

      {/* Empty state */}
      {!loading && scans.length === 0 && !error && (
        <div style={{
          background: 'rgba(80, 77, 154, 0.25)',
          border: '1px solid rgba(102, 196, 225, 0.2)',
          borderRadius: '1rem',
          padding: '3rem',
          textAlign: 'center',
        }}>
          <History size={48} color="#66c4e1" style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
          <h3 style={{ color: 'white', fontWeight: '600', margin: 0 }}>No scans yet</h3>
        </div>
      )}

      {/* Scan list */}
      {scans.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {scans.map((scan) => (
            <ScanCard key={scan.id} scan={scan} />
          ))}

          {/* Load more */}
          {hasMore && (
            <button
              onClick={() => loadScans(offset + LIMIT)}
              disabled={loading}
              style={{
                padding: '0.75rem',
                background: 'rgba(80, 77, 154, 0.25)',
                border: '1px solid rgba(102, 196, 225, 0.2)',
                borderRadius: '0.75rem',
                color: '#66c4e1',
                fontSize: '0.875rem',
                cursor: loading ? 'not-allowed' : 'pointer',
                fontWeight: '500',
                transition: 'border-color 0.2s ease, transform 0.2s ease',
              }}
              onMouseEnter={(e) => {
                if (!loading) {
                  e.currentTarget.style.borderColor = '#66c4e1';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }
              }}
              onMouseLeave={(e) => {
                if (!loading) {
                  e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)';
                  e.currentTarget.style.transform = 'translateY(0)';
                }
              }}
            >
              {loading ? 'Loading...' : 'Load More'}
            </button>
          )}
        </div>
      )}

      {/* API Keys Section */}
      <ApiKeysSection session={session} />
    </div>
  );
}
