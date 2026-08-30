import React from "react";
import {
  AlertTriangle,
  KeyRound,
  Share2,
  ShieldCheck,
  Target,
  Zap,
} from "lucide-react";

// One icon per check. Line icons from the same set the marketing pages use, so the
// scan flow reads as the same product (no emoji, which never match a brand palette
// and render differently on every platform).
const ICONS = {
  direct_prompt_injection: AlertTriangle,
  excessive_agency: Zap,
  data_exfiltration: Share2,
  system_prompt_leakage: KeyRound,
  instruction_following: Target,
};

/**
 * A check's icon inside the tinted rounded tile used across the site.
 * `size` controls the tile; pass `bare` to render just the glyph.
 */
export default function CheckIcon({ check, size = 40, bare = false, color }) {
  const Icon = ICONS[check] || ShieldCheck;
  const glyph = Math.round(size * 0.48);
  if (bare) return <Icon size={glyph} color={color || "var(--accent)"} aria-hidden />;
  return (
    <span
      aria-hidden
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: size * 0.3,
        background: "var(--brand-gradient-soft)",
        border: "1px solid var(--border)",
      }}
    >
      <Icon size={glyph} color={color || "var(--accent)"} />
    </span>
  );
}
