import { useEffect, useState } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Header, Footer } from "./components/layout";
import ErrorBoundary from "./components/layout/ErrorBoundary";
import { loadScanState, saveScanState } from "./lib/session";

// Scroll to top on route change
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
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
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "transparent", // the calm, theme-aware backdrop is painted on <body> (index.css)
      }}
    >
      <ScrollToTop />
      <Header />

      <main style={{ flex: 1 }}>
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
              <div
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "5rem 1rem",
                }}
              >
                <div style={{ textAlign: "center" }}>
                  <h1
                    style={{
                      fontSize: "2.5rem",
                      fontWeight: "bold",
                      color: "var(--text)",
                      marginBottom: "1rem",
                    }}
                  >
                    404
                  </h1>
                  <p style={{ color: "var(--muted)", marginBottom: "1.5rem" }}>
                    Page not found
                  </p>
                  <a
                    href="/"
                    style={{
                      color: "var(--accent-ink)",
                      textDecoration: "underline",
                    }}
                  >
                    Go back home
                  </a>
                </div>
              </div>
            }
          />
        </Routes>
        </ErrorBoundary>
      </main>

      <Footer />
    </div>
  );
}
