import { useEffect, useState } from "react";
import { Link, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Header, Footer } from "./components/layout";
import ErrorBoundary from "./components/layout/ErrorBoundary";
import { loadScanState, saveScanState } from "./lib/session";

// Scroll to top on route change, or to the #anchor when the link names one (/use#local).
function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    const target = hash && document.getElementById(decodeURIComponent(hash.slice(1)));
    if (target) target.scrollIntoView();
    else window.scrollTo(0, 0);
  }, [pathname, hash]);
  return null;
}

import Landing from "./pages/Landing";
import Scan from "./pages/Scan";
import Report from "./pages/Report";
import Privacy from "./pages/Privacy";
import Use from "./pages/Use";
import Trust from "./pages/Trust";

export default function App() {
  const location = useLocation();
  // Lifted to App so a report survives navigation; sessionStorage keeps it across a refresh.
  const [scanState, setScanState] = useState(loadScanState);
  useEffect(() => saveScanState(scanState), [scanState]);

  return (
    <div className="flex min-h-screen flex-col">
      <ScrollToTop />
      <Header />

      <main className="flex-1">
        <ErrorBoundary key={location.pathname}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route
            path="/scan"
            element={<Scan scanState={scanState} setScanState={setScanState} />}
          />
          <Route path="/report/:scanId" element={<Report />} />
          <Route path="/test" element={<Navigate to="/scan" replace />} />
          <Route path="/use" element={<Use />} />
          <Route path="/trust" element={<Trust />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Navigate to="/privacy" replace />} />

          <Route
            path="*"
            element={
              <article className="doc">
                <h1 className="doc-title">Page not found (404)</h1>
                <p className="mt-6">
                  <Link to="/" className="text-link">
                    Overview
                  </Link>
                </p>
              </article>
            }
          />
        </Routes>
        </ErrorBoundary>
      </main>

      <Footer />
    </div>
  );
}
