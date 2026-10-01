import { useEffect, useState } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
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

// Pages
import Landing from "./pages/Landing";
import Scan from "./pages/Scan";
import Report from "./pages/Report";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import Use from "./pages/Use";
import Trust from "./pages/Trust";

export default function App() {
  const location = useLocation();
  // Scan state lifted to App so a report survives navigation, and kept in sessionStorage so it
  // survives a refresh.
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
          {/* Preserve inbound links/SEO from the old tool route. */}
          <Route path="/test" element={<Navigate to="/scan" replace />} />
          <Route path="/use" element={<Use />} />
          <Route path="/trust" element={<Trust />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />

          <Route
            path="*"
            element={
              <article className="doc">
                <p className="eyebrow">404</p>
                <h1 className="doc-title">Page not found</h1>
                <p className="mt-6">
                  <a href="/" className="text-link">
                    Go to the overview
                  </a>
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
