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

const linkClass = ({ isActive }) =>
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
