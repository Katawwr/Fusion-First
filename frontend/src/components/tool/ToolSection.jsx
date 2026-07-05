import React, { useState, useCallback } from 'react';
import { Shield, Sparkles, Zap, RotateCcw } from 'lucide-react';
import SetupPanel from './SetupPanel';
import ResultsPanel from './ResultsPanel';
import FixesPanel from './FixesPanel';
import { runQualityScanStreaming } from '../../lib/api';

const tabs = [
  { id: 'setup', label: 'Setup', icon: Zap },
  { id: 'results', label: 'Results', icon: Shield },
  { id: 'fixes', label: 'Fixes', icon: Sparkles },
];

export default function ToolSection({
  freeCredits,
  setFreeCredits,
  toolState,
  setToolState,
  session,
}) {
  const { systemPrompt, results, activeTab } = toolState || {};
  const [testing, setTesting] = useState(false);
  const [streamingResults, setStreamingResults] = useState([]);
  const [streamingProgress, setStreamingProgress] = useState({ completed: 0, total: 20 });
  const [statusMessage, setStatusMessage] = useState('');

  const setSystemPrompt = (value) => setToolState(prev => ({ ...prev, systemPrompt: value }));
  const setResults = (value) => setToolState(prev => ({ ...prev, results: value }));
  const setActiveTab = (value) => setToolState(prev => ({ ...prev, activeTab: value }));

  const runQualityTest = useCallback(async () => {
    if (!systemPrompt) {
      alert('Please enter a system prompt');
      return;
    }

    if (freeCredits <= 0) {
      window.location.href = '/#pricing-section';
      return;
    }

    setTesting(true);
    setActiveTab('results');
    setResults(null);
    setStreamingResults([]);
    setStreamingProgress({ completed: 0, total: 20 });
    setStatusMessage('Connecting...');

    try {
      const accessToken = session?.access_token || null;
      let finalFixes = null;
      let finalPreventive = null;

      await runQualityScanStreaming(systemPrompt, '', {
        accessToken,
        onStatus: (data) => {
          setStatusMessage(data.message || '');
          if (data.total) {
            setStreamingProgress(prev => ({ ...prev, total: data.total }));
          }
        },
        onTestResult: (data) => {
          const result = data.result;
          setStreamingResults(prev => [...prev, result]);
          setStreamingProgress({ completed: data.completed, total: data.total });
        },
        onFixes: (data) => {
          finalFixes = data.fixes || '';
          finalPreventive = data.preventive_recommendations || null;
        },
        onSummary: (data) => {
          // Build the final results object matching the existing format
          setStreamingResults(currentResults => {
            setResults({
              success: true,
              summary: data.summary,
              results: currentResults,
              fixes: finalFixes,
              preventive_recommendations: finalPreventive,
              remaining_credits: data.remaining_credits,
            });
            return currentResults;
          });
          if (data.remaining_credits !== undefined) {
            setFreeCredits(data.remaining_credits);
          }
        },
        onComplete: () => {
          setTesting(false);
          setStatusMessage('');
        },
        onError: (data) => {
          alert(`Error: ${data.message || 'Scan failed'}`);
          setActiveTab('setup');
          setTesting(false);
          setStatusMessage('');
        },
      });

      // If stream ended without onComplete (connection closed cleanly)
      setTesting(false);
      setStatusMessage('');
    } catch (error) {
      alert(`Error: ${error.message}`);
      setActiveTab('setup');
      setTesting(false);
      setStatusMessage('');
    }
  }, [systemPrompt, freeCredits, session, setFreeCredits, setResults, setActiveTab]);

  const isResultsDisabled = !results && !testing && streamingResults.length === 0;
  const isFixesDisabled = !results || !results.fixes;

  const hasContent = (results || streamingResults.length > 0) && activeTab !== 'setup';

  const handleNewScan = () => {
    setToolState({ systemPrompt: '', results: null, activeTab: 'setup' });
    setStreamingResults([]);
    setStreamingProgress({ completed: 0, total: 20 });
    setStatusMessage('');
  };

  return (
    <section
      id="tool-section"
      style={{
        padding: 'clamp(2rem, 4vw, 4rem) 0'
      }}
    >
      <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
        {/* Tab Navigation */}
        <nav style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: 'clamp(0.5rem, 2vw, 1rem)',
          marginBottom: '2rem',
          flexWrap: 'wrap',
        }}>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isDisabled =
              (tab.id === 'results' && isResultsDisabled) ||
              (tab.id === 'fixes' && isFixesDisabled);
            const isActive = activeTab === tab.id;

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
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  whiteSpace: 'nowrap',
                  opacity: isDisabled ? 0.5 : 1
                }}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
          {hasContent && !testing && (
            <button
              onClick={handleNewScan}
              style={{
                padding: 'clamp(0.5rem, 2vw, 0.75rem) clamp(0.75rem, 3vw, 1.5rem)',
                fontWeight: '600',
                fontSize: 'clamp(0.875rem, 2vw, 1rem)',
                background: 'linear-gradient(to right, #f38f95, #db418b)',
                border: 'none',
                borderRadius: '0.5rem',
                color: 'white',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                whiteSpace: 'nowrap',
              }}
            >
              <RotateCcw size={16} />
              New Scan
            </button>
          )}
        </nav>

        {/* Tab Content */}
        <div style={{ minHeight: '400px' }}>
          {activeTab === 'setup' && (
            <SetupPanel
              systemPrompt={systemPrompt}
              setSystemPrompt={setSystemPrompt}
              onRunTest={runQualityTest}
              testing={testing}
              freeCredits={freeCredits}
            />
          )}

          {activeTab === 'results' && (
            <ResultsPanel
              results={results}
              testing={testing}
              streamingResults={streamingResults}
              progress={streamingProgress}
              statusMessage={statusMessage}
            />
          )}

          {activeTab === 'fixes' && (
            <FixesPanel fixes={results?.fixes} preventive_recommendations={results?.preventive_recommendations} />
          )}
        </div>
      </div>
    </section>
  );
}
