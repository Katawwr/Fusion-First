import { useState, useEffect, useCallback } from 'react';
import { fetchFreeCredits, fetchUserCredits } from '../lib/api';

export default function useCredits(session = null) {
  const [credits, setCredits] = useState(null);  // null = loading state
  const [totalCredits, setTotalCredits] = useState(null);
  const [isSubscriber, setIsSubscriber] = useState(false);
  const [userPlan, setUserPlan] = useState('free');
  const [creditsLoading, setCreditsLoading] = useState(true);

  const updateCredits = useCallback((data) => {
    if (data.credits_remaining !== undefined) {
      setCredits(data.credits_remaining);
    }
    if (data.remaining_credits !== undefined) {
      setCredits(data.remaining_credits);
    }
    if (data.credits_total !== undefined) {
      setTotalCredits(data.credits_total);
    }
    if (data.total_credits !== undefined) {
      setTotalCredits(data.total_credits);
    }
    if (data.plan && data.plan !== 'free') {
      setUserPlan(data.plan);
      setIsSubscriber(true);
    }
  }, []);

  const setSubscriberCredits = useCallback((data) => {
    setCredits(data.credits_remaining);
    setTotalCredits(data.credits_total);
    setIsSubscriber(true);
    setUserPlan(data.plan);
  }, []);

  const resetToFree = useCallback(() => {
    setIsSubscriber(false);
    setUserPlan('free');
  }, []);

  // Fetch credits based on auth state
  useEffect(() => {
    const loadCredits = async () => {
      setCreditsLoading(true);
      console.log('[useCredits] Loading credits, session:', session ? 'exists' : 'null', 'access_token:', session?.access_token ? 'exists' : 'null');
      try {
        if (session?.access_token) {
          // Authenticated user - fetch from user credits endpoint
          console.log('[useCredits] Fetching authenticated credits...');
          try {
            const data = await fetchUserCredits(session.access_token);
            console.log('[useCredits] Got authenticated credits:', data);
            setCredits(data.credits_remaining);
            setTotalCredits(data.credits_total);
            if (data.plan && data.plan !== 'free') {
              setUserPlan(data.plan);
              setIsSubscriber(true);
            } else {
              setUserPlan('free');
              setIsSubscriber(false);
            }
          } catch (error) {
            console.error('Failed to fetch user credits:', error);
            // Fall back to free credits on error
            await loadFreeCredits();
          }
        } else {
          // Not authenticated - use free credits
          await loadFreeCredits();
        }
      } catch (error) {
        console.error('Failed to fetch credits:', error);
      } finally {
        setCreditsLoading(false);
      }
    };

    const loadFreeCredits = async () => {
      const data = await fetchFreeCredits();
      setCredits(data.remaining_credits);
      setTotalCredits(data.total_credits || 2);
      setIsSubscriber(false);
      setUserPlan('free');
    };

    loadCredits();
  }, [session?.access_token]);

  // Refresh credits (useful after a scan or subscription change)
  const refreshCredits = useCallback(async () => {
    if (session?.access_token) {
      try {
        const data = await fetchUserCredits(session.access_token);
        setCredits(data.credits_remaining);
        setTotalCredits(data.credits_total);
        if (data.plan && data.plan !== 'free') {
          setUserPlan(data.plan);
          setIsSubscriber(true);
        }
      } catch (error) {
        console.error('Failed to refresh credits:', error);
      }
    }
  }, [session?.access_token]);

  return {
    credits,
    freeCredits: credits, // Alias for backwards compatibility
    totalCredits,
    isSubscriber,
    userPlan,
    creditsLoading,
    setCredits,
    setFreeCredits: setCredits, // Alias for backwards compatibility
    setSubscriberCredits,
    updateCredits,
    resetToFree,
    refreshCredits,
  };
}
