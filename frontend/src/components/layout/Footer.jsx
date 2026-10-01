import React from "react";
import { Link } from "react-router-dom";

// Minimal by owner decision: Privacy & Terms and the copyright line only.
export default function Footer() {
  return (
    <footer className="mt-auto border-t border-app-border">
      <nav
        aria-label="Footer"
        className="mx-auto flex max-w-[64rem] flex-wrap items-center justify-between gap-x-5 gap-y-2 px-4 py-6 text-xs text-app-subtle"
      >
        <Link to="/privacy" className="hover:text-app-text">
          Privacy &amp; Terms
        </Link>
        <span>© 2026 Fusion First</span>
      </nav>
    </footer>
  );
}
