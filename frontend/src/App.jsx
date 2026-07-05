import { useEffect, useState } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
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
import Test from './pages/Test';
import Privacy from './pages/Privacy';
import Terms from './pages/Terms';
import Blog from './pages/Blog';
import BlogPost from './pages/BlogPost';
import Contact from './pages/Contact';
import Dashboard from './pages/Dashboard';
import ScanDetail from './pages/ScanDetail';

export default function App() {
  // Auth state
  const { session } = useAuth();

  // Credits management - pass session for authenticated credits
  const {
    freeCredits,
    totalCredits,
    isSubscriber,
    userPlan,
    setFreeCredits,
  } = useCredits(session);

  // Tool state - lifted to App level to persist across navigation
  const [toolState, setToolState] = useState({
    systemPrompt: '',
    results: null,
    activeTab: 'setup',
  });

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      background: 'linear-gradient(135deg, #504d9a 0%, #66c4e1 50%, #504d9a 100%)'
    }}>
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
          <Route
            path="/test"
            element={
              <Test
                freeCredits={freeCredits}
                setFreeCredits={setFreeCredits}
                totalCredits={totalCredits}
                isSubscriber={isSubscriber}
                userPlan={userPlan}
                toolState={toolState}
                setToolState={setToolState}
                session={session}
              />
            }
          />
          <Route path="/dashboard" element={<Dashboard setToolState={setToolState} />} />
          <Route path="/dashboard/scan/:scanId" element={<ScanDetail />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/blog/:slug" element={<BlogPost />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />

          {/* 404 fallback */}
          <Route
            path="*"
            element={
              <div style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '5rem 1rem'
              }}>
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
