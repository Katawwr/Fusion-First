import React, { useEffect, useRef, useState } from 'react';
import { Check } from 'lucide-react';
import { PRICING_PLANS } from '../../lib/constants';
import { SignInModal } from '../auth';
import { useAuth } from '../../hooks';

export default function PricingSection({
  isSubscriber = false,
  userPlan = 'free',
  freeCredits = 0,
  totalCredits = 0,
}) {
  const { user, session, isAuthenticated, requestMagicLink, magicLinkSent, error: authError, loading: authLoading } = useAuth();
  const [signInModalOpen, setSignInModalOpen] = useState(false);
  const [pendingCheckoutUrl, setPendingCheckoutUrl] = useState(null);
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.1 }
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => observer.disconnect();
  }, []);

  // Handle checkout - require login first
  const handleCheckout = (plan) => {
    if (!isAuthenticated) {
      // Store the checkout URL to redirect after login
      setPendingCheckoutUrl(plan.checkoutUrl);
      setSignInModalOpen(true);
      return;
    }
    // User is logged in - redirect to checkout with email and user_id prefilled
    const checkoutUrl = new URL(plan.checkoutUrl);
    if (user?.email) {
      checkoutUrl.searchParams.set('checkout[email]', user.email);
    }
    if (user?.id) {
      // Pass user_id as custom data for webhook to auto-link subscription
      checkoutUrl.searchParams.set('checkout[custom][user_id]', user.id);
    }
    window.open(checkoutUrl.toString(), '_blank');
  };

  // Handle magic link request
  const handleRequestMagicLink = async (email, marketingOptIn) => {
    await requestMagicLink(email, marketingOptIn);
    // Don't close modal - show success state instead
  };

  // When user logs in and we have a pending checkout, redirect
  useEffect(() => {
    if (isAuthenticated && pendingCheckoutUrl && user?.email) {
      const checkoutUrl = new URL(pendingCheckoutUrl);
      checkoutUrl.searchParams.set('checkout[email]', user.email);
      if (user?.id) {
        checkoutUrl.searchParams.set('checkout[custom][user_id]', user.id);
      }
      window.open(checkoutUrl.toString(), '_blank');
      setPendingCheckoutUrl(null);
    }
  }, [isAuthenticated, pendingCheckoutUrl, user?.email, user?.id]);

  return (
    <>
    <section
      ref={sectionRef}
      id="pricing-section"
      style={{
        padding: 'clamp(3rem, 6vw, 5rem) 0',
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
        transition: 'opacity 0.6s ease-out, transform 0.6s ease-out'
      }}
    >
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 1rem' }}>
        {/* Section header */}
        <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
          <h2 style={{
            fontSize: 'clamp(1.75rem, 4vw, 2.5rem)',
            fontWeight: 'bold',
            color: 'white',
            marginBottom: '1rem'
          }}>
            Simple, Transparent Pricing
          </h2>
        </div>

        {/* Pricing cards */}
        <div
          className="pricing-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '1.5rem',
            justifyItems: 'center'
          }}
        >
          <style>{`
            @media (max-width: 900px) {
              .pricing-grid > div:last-child:nth-child(odd) {
                grid-column: 1 / -1;
                max-width: 350px;
              }
            }
          `}</style>
          {PRICING_PLANS.map((plan, index) => (
            <div
              key={plan.name}
              style={{
                width: '100%',
                maxWidth: '350px',
                background: plan.popular
                  ? 'linear-gradient(135deg, rgba(102, 196, 225, 0.2), rgba(243, 143, 149, 0.2))'
                  : 'rgba(80, 77, 154, 0.4)',
                border: plan.popular ? '2px solid #f38f95' : '1px solid rgba(102, 196, 225, 0.3)',
                borderRadius: '1rem',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                position: 'relative',
                transition: 'border-color 0.2s ease, transform 0.2s ease',
                opacity: isVisible ? 1 : 0,
                transform: isVisible ? 'translateY(0)' : 'translateY(20px)',
                transitionDelay: `${index * 0.1}s`
              }}
              onMouseEnter={(e) => {
                if (!plan.popular) {
                  e.currentTarget.style.borderColor = '#66c4e1';
                }
                e.currentTarget.style.transform = 'translateY(-5px)';
              }}
              onMouseLeave={(e) => {
                if (!plan.popular) {
                  e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.3)';
                }
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              {plan.popular && (
                <div style={{
                  position: 'absolute',
                  top: '-12px',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  background: 'linear-gradient(to right, #f38f95, #db418b)',
                  padding: '0.25rem 1rem',
                  borderRadius: '1rem',
                  fontSize: '0.75rem',
                  fontWeight: 'bold',
                  color: 'white',
                  whiteSpace: 'nowrap'
                }}>
                  MOST POPULAR
                </div>
              )}

              <h3 style={{
                fontSize: '1.25rem',
                fontWeight: 'bold',
                color: plan.popular ? '#f38f95' : '#66c4e1',
                marginBottom: '0.5rem',
                marginTop: plan.popular ? '0.5rem' : 0
              }}>
                {plan.name}
              </h3>

              <div style={{ marginBottom: '1rem' }}>
                <span style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'white' }}>${plan.price}</span>
                <span style={{ color: 'white', fontSize: '0.875rem' }}>/month</span>
              </div>

              <p style={{ color: plan.popular ? '#f38f95' : '#66c4e1', fontSize: '0.875rem', marginBottom: '1rem' }}>
                {plan.credits} scans/month
              </p>

              <ul style={{ color: 'white', fontSize: '0.875rem', lineHeight: '1.8', paddingLeft: '0', listStyle: 'none', marginBottom: '1rem', flex: 1 }}>
                {plan.features.map((feature, idx) => (
                  <li key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <Check size={18} color="#66c4e1" style={{ flexShrink: 0, marginTop: '2px' }} />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              <button
                onClick={() => handleCheckout(plan)}
                style={{
                  display: 'block',
                  width: '100%',
                  padding: '0.75rem',
                  background: plan.popular ? 'linear-gradient(to right, #f38f95, #db418b)' : 'rgba(102, 196, 225, 0.2)',
                  border: plan.popular ? 'none' : '1px solid rgba(102, 196, 225, 0.5)',
                  borderRadius: '0.5rem',
                  color: plan.popular ? 'white' : '#66c4e1',
                  fontWeight: 'bold',
                  fontSize: '0.875rem',
                  textDecoration: 'none',
                  textAlign: 'center',
                  cursor: 'pointer',
                  transition: 'transform 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                Get {plan.name}
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>

    {/* Sign In Modal for checkout flow */}
    <SignInModal
      isOpen={signInModalOpen}
      onClose={() => {
        setSignInModalOpen(false);
        setPendingCheckoutUrl(null);
      }}
      onRequestMagicLink={handleRequestMagicLink}
      loading={authLoading}
      magicLinkSent={magicLinkSent}
      error={authError}
      session={session}
    />
    </>
  );
}
