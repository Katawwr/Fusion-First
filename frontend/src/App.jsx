import { useEffect, useState } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Header, Footer } from './components/layout';
import { useCredits, useAuth } from './hooks';

// Scroll to top on route change
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

// Pages
import Landing from './pages/Landing';
import Scan from './pages/Scan';
import Report from './pages/Report';
import Privacy from './pages/Privacy';
import Terms from './pages/Terms';
import Dashboard from './pages/Dashboard';
import ScanDetail from './pages/ScanDetail';

export default function App() {
  const { session } = useAuth();

  // Legacy credits — still feeds the (soon-to-be-rewritten) Landing page.
  const { freeCredits, totalCredits, isSubscriber, userPlan, setFreeCredits } = useCredits(session);

  // Scan state lifted to App so a report survives navigation (same pattern as the old tool state).
  const [scanState, setScanState] = useState({ systemPrompt: '', result: null });

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: 'transparent', // the calm, theme-aware backdrop is painted on <body> (index.css)
      }}
    >
      <ScrollToTop />
      <Header />

      <main style={{ flex: 1 }}>
        <Routes>
          <Route
            path="/"
            element={
              <Landing
                freeCredits={freeCredits}
                setFreeCredits={setFreeCredits}
                totalCredits={totalCredits}
                isSubscriber={isSubscriber}
                userPlan={userPlan}
              />
            }
          />
          <Route path="/scan" element={<Scan scanState={scanState} setScanState={setScanState} />} />
          <Route path="/report/:scanId" element={<Report />} />
          {/* Preserve inbound links/SEO from the old tool route. */}
          <Route path="/test" element={<Navigate to="/scan" replace />} />
          <Route path="/dashboard" element={<Dashboard setToolState={setScanState} />} />
          <Route path="/dashboard/scan/:scanId" element={<ScanDetail />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />

          <Route
            path="*"
            element={
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '5rem 1rem',
                }}
              >
                <div style={{ textAlign: 'center' }}>
                  <h1 style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'white', marginBottom: '1rem' }}>404</h1>
                  <p style={{ color: 'white', marginBottom: '1.5rem' }}>Page not found</p>
                  <a href="/" style={{ color: '#66c4e1', textDecoration: 'underline' }}>
                    Go back home
                  </a>
                </div>
              </div>
            }
          />
        </Routes>
      </main>

      <Footer />
    </div>
  );
}
