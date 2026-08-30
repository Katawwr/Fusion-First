// API Configuration
export const API_URL =
  "https://katawwr--fusion-quality-tester-fastapi-app.modal.run";

// Supabase Configuration
export const SUPABASE_URL = "https://redacted-legacy-project.supabase.co";
// Note: Use the anon/public key here, NOT the service role key
// The service role key should only be used on the backend
export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || "";

// Pricing Plans
export const PRICING_PLANS = [
  {
    name: "Starter",
    price: 19,
    credits: 25,
    features: [
      "25 real scans per month",
      "All safety checks + quality grading",
      "Open-weight & frontier models (Ollama, Claude, GPT)",
      "One-click hardened prompt + guardrail SDK",
    ],
    checkoutUrl:
      "https://fusion-first.lemonsqueezy.com/checkout/buy/ec839731-7209-43b5-ad87-a8699de5190b",
    popular: false,
  },
  {
    name: "Pro",
    price: 49,
    credits: 75,
    features: [
      "75 real scans per month",
      "Everything in Starter",
      "Before/after proof with confidence intervals",
      "Shareable & exportable HTML report cards",
    ],
    checkoutUrl:
      "https://fusion-first.lemonsqueezy.com/checkout/buy/4c8eda2e-b327-423f-aa81-984b1c2eac30",
    popular: true,
  },
  {
    name: "Team",
    price: 149,
    credits: 250,
    features: [
      "250 real scans per month",
      "Everything in Pro",
      "Full attack tiers (more probes per check)",
      "Early access to new safety checks",
    ],
    checkoutUrl:
      "https://fusion-first.lemonsqueezy.com/checkout/buy/a0572e97-6921-4c97-9cc6-1ee5efa919a6",
    popular: false,
  },
];

// Test Categories
export const TEST_CATEGORIES = [
  {
    id: "AMB",
    name: "Ambiguity",
    description: "Tests for handling vague or conflicting requests",
  },
  {
    id: "HAL",
    name: "Hallucination",
    description: "Tests for fabricated information or false claims",
  },
  {
    id: "BOUND",
    name: "Boundary Violations",
    description: "Tests for inappropriate advice (medical, legal, financial)",
  },
  {
    id: "MANIP",
    name: "Manipulation",
    description: "Tests for social engineering and exploitation attempts",
  },
  {
    id: "GAP",
    name: "Gap Testing",
    description: "Tests for off-topic requests and scope creep",
  },
  {
    id: "LOGIC",
    name: "Logical Consistency",
    description: "Tests for contradictions and impossible requests",
  },
  {
    id: "TONE",
    name: "Tone & Efficiency",
    description: "Tests for appropriate response tone and de-escalation",
  },
];

// Severity Levels
export const SEVERITY_COLORS = {
  critical: "bg-severity-critical",
  high: "bg-severity-high",
  medium: "bg-severity-medium",
  low: "bg-severity-low",
};
