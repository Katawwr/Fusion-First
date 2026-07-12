import { createClient } from '@supabase/supabase-js';
import { SUPABASE_URL, SUPABASE_ANON_KEY } from './constants';

// Fusion is demo-first: the whole scan → report → fix → prove flow is anonymous and needs no
// account. Auth (magic-link sign-in, saved history) is a progressive enhancement that only turns
// on when Supabase credentials are present. When they are missing we MUST NOT call createClient
// with an empty key — supabase-js throws "supabaseKey is required" at module load, which would
// crash the entire app to a blank page. Instead we export a harmless stub and a config flag.

export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

const AUTH_DISABLED = new Error('Sign-in is not configured for this deployment.');

// A no-op client shaped just enough to satisfy the calls in useAuth/useCredits without throwing.
function createStubClient() {
  return {
    auth: {
      async getSession() {
        return { data: { session: null }, error: null };
      },
      async getUser() {
        return { data: { user: null }, error: null };
      },
      onAuthStateChange() {
        return { data: { subscription: { unsubscribe() {} } } };
      },
      async signInWithOtp() {
        return { data: null, error: AUTH_DISABLED };
      },
      async signOut() {
        return { error: null };
      },
    },
  };
}

// A single supabase client (real when configured, stub otherwise) for interacting with auth.
export const supabase = isSupabaseConfigured
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : createStubClient();

// Helper to get the current session
export async function getSession() {
  const { data: { session }, error } = await supabase.auth.getSession();
  if (error) {
    console.error('Error getting session:', error);
    return null;
  }
  return session;
}

// Helper to get the current user
export async function getCurrentUser() {
  const { data: { user }, error } = await supabase.auth.getUser();
  if (error) {
    console.error('Error getting user:', error);
    return null;
  }
  return user;
}

// Send magic link email for sign-in
export async function sendMagicLink(email) {
  if (!isSupabaseConfigured) {
    throw AUTH_DISABLED;
  }
  const { data, error } = await supabase.auth.signInWithOtp({
    email: email,
    options: {
      emailRedirectTo: `${window.location.origin}/scan`,
    },
  });

  if (error) {
    console.error('Error sending magic link:', error);
    throw error;
  }

  return data;
}

// Sign out
export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) {
    console.error('Error signing out:', error);
    throw error;
  }
}
