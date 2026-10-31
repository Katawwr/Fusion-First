import React, { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Menu, X, Sun, Moon } from "lucide-react";
import { useTheme } from "../../hooks";
import BrandMark from "./BrandMark";

const NAV_LINKS = [
  { name: "Overview", href: "/" },
  { name: "Scan", href: "/scan" },
  { name: "Use", href: "/use" },
  { name: "Trust", href: "/trust" },
];

const REPO_URL = "https://github.com/Katawwr/Fusion-First";

// GitHub's mark (Octicons mark-github), inline so the header needs no brand-icon package.
const GitHubMark = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
  </svg>
);

const linkClass =({ isActive }) =>
  `px-2 py-1 text-sm transition-colors ${
    isActive ? "nav-active font-medium" : "text-app-muted hover:text-app-text"
  }`;

export default function Header() {
  const [open, setOpen] = useState(false);
  const { effective, toggle } = useTheme();
  const themeLabel = effective === "dark" ? "Switch to light mode" : "Switch to dark mode";

  return (
    <header
      className="sticky top-0 z-50 border-b border-app-border"
      style={{ background: "color-mix(in srgb, var(--bg) 88%, transparent)", backdropFilter: "blur(8px)" }}
    >
      <div className="mx-auto flex h-14 max-w-[64rem] items-center justify-between gap-4 px-4">
        <Link to="/" className="flex items-center gap-2.5 no-underline" aria-label="Fusion First, overview">
          <BrandMark />
          <span className="brand-wordmark text-app-text">Fusion First</span>
        </Link>

        <nav aria-label="Main" className="hidden items-center gap-1.5 md:flex">
          {NAV_LINKS.map((l) => (
            <NavLink key={l.href} to={l.href} end={l.href === "/"} className={linkClass}>
              {l.name}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-1.5">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Source on GitHub"
            title="Source on GitHub"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-app-border text-app-muted hover:text-app-text"
          >
            <GitHubMark />
          </a>
          <button
            type="button"
            onClick={toggle}
            aria-label={themeLabel}
            title={themeLabel}
            className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-md border border-app-border text-app-muted hover:text-app-text"
          >
            {effective === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button
            type="button"
            className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-md text-app-text md:hidden"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {open && (
        <nav aria-label="Main" className="border-t border-app-border px-4 py-3 md:hidden">
          <ul className="flex flex-col">
            {NAV_LINKS.map((l) => (
              <li key={l.href}>
                <NavLink
                  to={l.href}
                  end={l.href === "/"}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `block py-2 text-[0.95rem] ${isActive ? "nav-active font-medium" : "text-app-muted"}`
                  }
                >
                  {l.name}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}
