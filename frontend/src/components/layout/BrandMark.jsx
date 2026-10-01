import React from "react";

// The FF monogram (owner, 2026-10-01): "FF" = friendly fire. It replaces logo.png; set in the title face so it
// matches the wordmark. The second F takes the brand pink.
export default function BrandMark({ size = 28 }) {
  return (
    <span aria-hidden className="brand-mark" style={{ width: size, height: size, fontSize: size * 0.54 }}>
      F<span className="brand-mark-fire">F</span>
    </span>
  );
}
