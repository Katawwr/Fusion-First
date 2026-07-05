import React from 'react';
import { Loader } from 'lucide-react';
import VulnerabilityCard from './VulnerabilityCard';

function SeverityCard({ count, label, bgColor, borderColor, textColor, hoverBorderColor }) {
  return (
    <div
      style={{
        background: bgColor,
        border: `1px solid ${borderColor}`,
        borderRadius: '0.75rem',
        padding: 'clamp(1rem, 2vw, 1.5rem)',
        transition: 'border-color 0.2s ease, transform 0.2s ease'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = hoverBorderColor || textColor;
        e.currentTarget.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = borderColor;
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      <div style={{ fontSize: 'clamp(1.5rem, 4vw, 2.25rem)', fontWeight: 'bold', color: textColor }}>
        {count}
      </div>
      <div style={{ fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)', color: 'white', marginTop: '0.25rem' }}>
        {label}
      </div>
    </div>
  );
}

function ProgressBar({ completed, total, statusMessage }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Loader size={16} color="#66c4e1" style={{ animation: 'spin 1s linear infinite' }} />
          <span style={{ color: 'white', fontSize: 'clamp(0.875rem, 2vw, 1rem)', fontWeight: '600' }}>
            {statusMessage || `Testing ${completed}/${total}...`}
          </span>
        </div>
        <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem' }}>
          {pct}%
        </span>
      </div>
      <div style={{
        width: '100%',
        height: '6px',
        background: 'rgba(255,255,255,0.1)',
        borderRadius: '3px',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: 'linear-gradient(to right, #66c4e1, #f38f95)',
          borderRadius: '3px',
          transition: 'width 0.3s ease',
        }} />
      </div>
    </div>
  );
}

function computeSeverityCounts(resultsList) {
  const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, SUGGESTIONS: 0 };
  for (const r of resultsList) {
    if (r.finding_type === 'suggestion') {
      counts.SUGGESTIONS++;
    } else if (r.is_issue && counts[r.severity] !== undefined) {
      counts[r.severity]++;
    }
  }
  return counts;
}

export default function ResultsPanel({ results, testing, streamingResults = [], progress = {}, statusMessage = '' }) {
  // Determine which results to show: final results if available, otherwise streaming
  const isStreaming = testing && streamingResults.length > 0;
  const displayResults = results?.results || (isStreaming ? streamingResults : []);
  const bySeverity = results?.summary?.by_severity || (isStreaming ? computeSeverityCounts(streamingResults) : {});

  // Pure loading state — no results yet, still testing
  if (testing && streamingResults.length === 0) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'clamp(3rem, 5vw, 5rem) 0'
      }}>
        <Loader size={70} color="#66c4e1" style={{ animation: 'spin 1s linear infinite', marginBottom: '1.5rem' }} />
        <p style={{ fontSize: 'clamp(1.25rem, 3vw, 1.5rem)', fontWeight: '600', marginBottom: '0.5rem', textAlign: 'center', color: 'white' }}>
          {statusMessage || 'Preparing scan...'}
        </p>
        <p style={{ fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)', color: 'white', marginTop: '1rem', textAlign: 'center' }}>
          Results will appear here as each test completes.
        </p>
      </div>
    );
  }

  if (!testing && !results && streamingResults.length === 0) {
    return null;
  }

  const issueCount = displayResults.filter(r => r.is_issue && r.finding_type !== 'suggestion').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Progress bar during streaming */}
      {isStreaming && (
        <ProgressBar
          completed={progress.completed || 0}
          total={progress.total || 20}
          statusMessage={statusMessage}
        />
      )}

      {/* Summary Cards - Issues by Severity */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))',
        gap: '1rem'
      }}>
        <SeverityCard
          count={bySeverity.CRITICAL || 0}
          label="Critical"
          bgColor="rgba(239, 68, 68, 0.15)"
          borderColor="rgba(239, 68, 68, 0.4)"
          textColor="#ef4444"
          hoverBorderColor="#ef4444"
        />
        <SeverityCard
          count={bySeverity.HIGH || 0}
          label="High"
          bgColor="rgba(251, 146, 60, 0.15)"
          borderColor="rgba(251, 146, 60, 0.4)"
          textColor="#fb923c"
          hoverBorderColor="#fb923c"
        />
        <SeverityCard
          count={bySeverity.MEDIUM || 0}
          label="Medium"
          bgColor="rgba(250, 204, 21, 0.15)"
          borderColor="rgba(250, 204, 21, 0.4)"
          textColor="#facc15"
          hoverBorderColor="#facc15"
        />
        <SeverityCard
          count={bySeverity.LOW || 0}
          label="Low"
          bgColor="rgba(34, 197, 94, 0.1)"
          borderColor="rgba(34, 197, 94, 0.3)"
          textColor="#22c55e"
          hoverBorderColor="#22c55e"
        />
        <SeverityCard
          count={bySeverity.SUGGESTIONS || 0}
          label="Suggestions"
          bgColor="rgba(102, 196, 225, 0.1)"
          borderColor="rgba(102, 196, 225, 0.3)"
          textColor="#66c4e1"
          hoverBorderColor="#66c4e1"
        />
      </div>

      {/* Vulnerabilities List */}
      <div>
        <h2 style={{ fontSize: 'clamp(1.25rem, 3vw, 1.5rem)', fontWeight: 'bold', marginBottom: '1rem', color: 'white' }}>
          Test Results
          {isStreaming && (
            <span style={{ fontSize: '0.875rem', fontWeight: '400', color: 'rgba(255,255,255,0.5)', marginLeft: '0.75rem' }}>
              {issueCount} issue{issueCount !== 1 ? 's' : ''} found so far
            </span>
          )}
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {displayResults.map((vuln, idx) => (
            <VulnerabilityCard
              key={`${vuln.test_id}-${idx}`}
              vulnerability={vuln}
              index={idx}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
