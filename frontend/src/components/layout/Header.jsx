import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Menu, X, LogOut } from 'lucide-react';
import { SignInModal } from '../auth';
import { useAuth } from '../../hooks';

export default function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [signInModalOpen, setSignInModalOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, session, loading: authLoading, requestMagicLink, magicLinkSent, error: authError, signOut, isAuthenticated } = useAuth();

  const navLinks = [
    { name: 'Home', href: '/' },
    { name: 'Test', href: '/test' },
    { name: 'Dashboard', href: '/dashboard' },
    { name: 'Guides', href: '/blog' },
    { name: 'Contact', href: '/contact' },
  ];

  const handleRequestMagicLink = async (email, marketingOptIn) => {
    await requestMagicLink(email, marketingOptIn);
    // Don't close modal - show success state instead
  };

  const handleSignOut = async () => {
    await signOut();
    setMobileMenuOpen(false);
  };

  return (
    <>
      <header style={{
        borderBottom: '1px solid rgba(255,255,255,0.1)',
        background: 'rgba(0,0,0,0.3)',
        backdropFilter: 'blur(10px)',
        position: 'sticky',
        top: 0,
        zIndex: 50
      }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: 'clamp(0.75rem, 2vw, 1rem) 1rem' }}>
          <div
            className="header-row"
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr auto 1fr',
              alignItems: 'center',
              gap: 'clamp(0.5rem, 2vw, 1rem)'
            }}
          >
            {/* Logo - Left */}
            <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 'clamp(0.75rem, 2.5vw, 1.25rem)', textDecoration: 'none' }}>
              <div style={{
                position: 'relative',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 'clamp(48px, 12vw, 64px)',
                height: 'clamp(48px, 12vw, 64px)',
                flexShrink: 0
              }}>
                <img
                  src="/logo.png"
                  alt="Fusion First"
                  style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                  onError={(e) => {
                    e.target.style.display = 'none';
                    e.target.parentElement.innerHTML = '<div style="width: 100%; height: 100%; background: linear-gradient(135deg, #66c4e1, #504d9a); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; font-size: clamp(24px, 6vw, 32px);">F</div>';
                  }}
                />
              </div>
              <h1 style={{
                fontSize: 'clamp(1.25rem, 5vw, 2rem)',
                fontWeight: 'bold',
                background: 'linear-gradient(to right, #66c4e1, #f38f95)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                margin: 0,
                lineHeight: 1
              }}>
                Fusion First
              </h1>
            </Link>

            {/* Desktop Navigation - Center */}
            <nav className="hidden md:flex" style={{ alignItems: 'center', justifyContent: 'center', gap: '2rem' }}>
              {navLinks.map((link) => (
                <Link
                  key={link.name}
                  to={link.href}
                  style={{
                    fontSize: '0.875rem',
                    fontWeight: '500',
                    color: location.pathname === link.href ? '#f38f95' : 'white',
                    textDecoration: 'none',
                    transition: 'color 0.2s'
                  }}
                >
                  {link.name}
                </Link>
              ))}
            </nav>

            {/* Right side - Sign In button */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '1rem' }}>
              {/* Desktop Auth */}
              {isAuthenticated ? (
                <div className="hidden md:flex" style={{ alignItems: 'center', gap: '0.75rem' }}>
                  <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.875rem' }}>
                    {user?.email?.split('@')[0]}
                  </span>
                  <button
                    onClick={handleSignOut}
                    style={{
                      padding: '0.5rem 1rem',
                      background: 'transparent',
                      border: '1px solid rgba(255,255,255,0.3)',
                      borderRadius: '0.5rem',
                      color: 'white',
                      fontSize: '0.875rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem'
                    }}
                  >
                    <LogOut size={16} />
                    Sign Out
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setSignInModalOpen(true)}
                  className="hidden md:block"
                  style={{
                    padding: '0.5rem 1rem',
                    background: 'linear-gradient(to right, #f38f95, #db418b)',
                    border: 'none',
                    borderRadius: '0.5rem',
                    color: 'white',
                    fontWeight: 'bold',
                    fontSize: '0.875rem',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap'
                  }}
                >
                  Sign In
                </button>
              )}

              {/* Mobile menu button */}
              <button
                className="md:hidden"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                style={{
                  padding: '0.5rem',
                  background: 'none',
                  border: 'none',
                  color: 'white',
                  cursor: 'pointer'
                }}
              >
                {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
              </button>
            </div>
          </div>

          {/* Mobile Navigation */}
          {mobileMenuOpen && (
            <div className="md:hidden" style={{ paddingTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)', marginTop: '1rem' }}>
              <nav style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {navLinks.map((link) => (
                  <Link
                    key={link.name}
                    to={link.href}
                    onClick={() => setMobileMenuOpen(false)}
                    style={{
                      fontSize: '0.875rem',
                      fontWeight: '500',
                      color: location.pathname === link.href ? '#f38f95' : 'white',
                      textDecoration: 'none'
                    }}
                  >
                    {link.name}
                  </Link>
                ))}
                {isAuthenticated ? (
                  <>
                    <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.875rem', margin: 0 }}>
                      {user?.email}
                    </p>
                    <button
                      onClick={handleSignOut}
                      style={{
                        padding: '0.75rem',
                        background: 'transparent',
                        border: '1px solid rgba(255,255,255,0.3)',
                        borderRadius: '0.5rem',
                        color: 'white',
                        fontSize: '0.875rem',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '0.5rem',
                        width: '100%'
                      }}
                    >
                      <LogOut size={16} />
                      Sign Out
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => {
                      setMobileMenuOpen(false);
                      setSignInModalOpen(true);
                    }}
                    style={{
                      padding: '0.75rem',
                      background: 'linear-gradient(to right, #f38f95, #db418b)',
                      border: 'none',
                      borderRadius: '0.5rem',
                      color: 'white',
                      fontWeight: 'bold',
                      fontSize: '0.875rem',
                      cursor: 'pointer',
                      width: '100%'
                    }}
                  >
                    Sign In
                  </button>
                )}
              </nav>
            </div>
          )}
        </div>
      </header>

      {/* Sign In Modal */}
      <SignInModal
        isOpen={signInModalOpen}
        onClose={() => setSignInModalOpen(false)}
        onRequestMagicLink={handleRequestMagicLink}
        loading={authLoading}
        magicLinkSent={magicLinkSent}
        error={authError}
        session={session}
      />
    </>
  );
}
