import React from "react";
import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="mt-auto border-t border-app-border">
      <div className="mx-auto flex max-w-[64rem] flex-col gap-3 px-4 py-6 text-xs text-app-subtle sm:flex-row sm:items-center sm:justify-between">
        <p>
          <span className="brand-wordmark text-[1rem] text-app-muted">Fusion First</span>
          <span> · numbers are generated from committed evidence</span>
        </p>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-2">
          <Link to="/privacy" className="hover:text-app-text">
            Privacy &amp; Terms
          </Link>
          <span>© 2026 Fusion First</span>
        </nav>
      </div>
    </footer>
  );
}
