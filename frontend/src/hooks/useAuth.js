import { useState, useEffect, useCallback } from "react";
import {
  supabase,
  sendMagicLink,
  signOut as supabaseSignOut,
  getSession,
} from "../lib/supabase";
import { API_URL } from "../lib/constants";

export default function useAuth() {
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [magicLinkSent, setMagicLinkSent] = useState(false);

  useEffect(() => {
    // Get initial session
    getSession().then((session) => {
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    });

    // Listen for auth state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      console.log("[Auth] State changed:", event);
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
      setMagicLinkSent(false);

      // If user just signed in, record login event and apply marketing preference
      if (event === "SIGNED_IN" && session?.user) {
        console.log("[Auth] User signed in:", session.user.email);

        // Record login event
        try {
          await fetch(`${API_URL}/api/user/login-event`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${session.access_token}`,
            },
          });
        } catch (e) {
          console.log("[Auth] Failed to record login event:", e);
        }

        // Apply pending marketing preference if any
        const pendingOptIn = localStorage.getItem(
          "fusion_pending_marketing_opt_in",
        );
        if (pendingOptIn !== null) {
          localStorage.removeItem("fusion_pending_marketing_opt_in");
          try {
            await fetch(`${API_URL}/api/user/marketing-preferences`, {
              method: "POST",
              headers: {
                Authorization: `Bearer ${session.access_token}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                marketing_opt_in: pendingOptIn === "true",
              }),
            });
            console.log(
              "[Auth] Marketing preference saved:",
              pendingOptIn === "true",
            );
          } catch (e) {
            console.log("[Auth] Failed to save marketing preference:", e);
          }
        }
      }
    });

    return () => {
      subscription?.unsubscribe();
    };
  }, []);

  const requestMagicLink = useCallback(
    async (email, marketingOptIn = false) => {
      setError(null);
      setLoading(true);
      setMagicLinkSent(false);
      try {
        // Store marketing preference to apply after sign-in
        localStorage.setItem(
          "fusion_pending_marketing_opt_in",
          String(marketingOptIn),
        );

        await sendMagicLink(email);
        setMagicLinkSent(true);
      } catch (err) {
        setError(err.message || "Failed to send magic link");
        // Clear pending preference on error
        localStorage.removeItem("fusion_pending_marketing_opt_in");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const signOut = useCallback(async () => {
    setError(null);
    try {
      await supabaseSignOut();
      setUser(null);
      setSession(null);
    } catch (err) {
      setError(err.message || "Failed to sign out");
    }
  }, []);

  // Get the access token for API calls
  const getAccessToken = useCallback(async () => {
    if (!session) return null;
    return session.access_token;
  }, [session]);

  return {
    user,
    session,
    loading,
    error,
    isAuthenticated: !!user,
    magicLinkSent,
    requestMagicLink,
    signOut,
    getAccessToken,
  };
}
