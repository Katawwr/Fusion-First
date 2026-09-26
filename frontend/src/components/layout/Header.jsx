import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu, X, Sun, Moon } from "lucide-react";
import { useTheme } from "../../hooks";

// No accounts, no billing: Fusion runs locally (CLI / MCP / plugin) or as a keyless demo here.
const NAV_LINKS = [
  { name: "Home", href: "/" },
  { name: "Scan", href: "/scan" },
];

const ctaStyle = {
  padding: "0.5rem 1rem",
  background: "linear-gradient(to right, #f38f95, #db418b)",
  borderRadius: "0.5rem",
  color: "#fff",
  fontWeight: "bold",
  fontSize: "0.875rem",
  textDecoration: "none",
  whiteSpace: "nowrap",
};

export default function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [logoOk, setLogoOk] = useState(true);
  const location = useLocation();
  const { effective, toggle } = useTheme();
  const themeLabel =
    effective === "dark" ? "Switch to light mode" : "Switch to dark mode";

  return (
    <header
      style={{
        borderBottom: "1px solid var(--border)",
        background: "color-mix(in srgb, var(--bg-elev) 82%, transparent)",
        backdropFilter: "blur(10px)",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "clamp(0.75rem, 2vw, 1rem) 1rem",
        }}
      >
        <div
          className="header-row"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto 1fr",
            alignItems: "center",
            gap: "clamp(0.5rem, 2vw, 1rem)",
          }}
        >
          {/* Logo - Left */}
          <Link
            to="/"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "clamp(0.75rem, 2.5vw, 1.25rem)",
              textDecoration: "none",
            }}
          >
            <div
              style={{
                position: "relative",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: "clamp(48px, 12vw, 64px)",
                height: "clamp(48px, 12vw, 64px)",
                flexShrink: 0,
              }}
            >
              {logoOk ? (
                <img
                  src="/logo.png"
                  alt="Fusion First"
                  style={{ width: "100%", height: "100%", objectFit: "contain" }}
                  onError={() => setLogoOk(false)}
                />
              ) : (
                <div
                  aria-label="Fusion First"
                  style={{
                    width: "100%",
                    height: "100%",
                    background: "linear-gradient(135deg, #66c4e1, #504d9a)",
                    borderRadius: "10px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: "bold",
                    color: "white",
                    fontSize: "clamp(24px, 6vw, 32px)",
                  }}
                >
                  F
                </div>
              )}
            </div>
            <h1
              style={{
                fontSize: "clamp(1.25rem, 5vw, 2rem)",
                fontWeight: "bold",
                background: "linear-gradient(to right, #66c4e1, #f38f95)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                margin: 0,
                lineHeight: 1,
              }}
            >
              Fusion First
            </h1>
          </Link>

          {/* Desktop Navigation - Center */}
          <nav
            className="hidden md:flex"
            style={{ alignItems: "center", justifyContent: "center", gap: "2rem" }}
          >
            {NAV_LINKS.map((link) => (
              <Link
                key={link.name}
                to={link.href}
                style={{
                  fontSize: "0.875rem",
                  fontWeight: "500",
                  color:
                    location.pathname === link.href
                      ? "var(--pink-ink)"
                      : "var(--text)",
                  textDecoration: "none",
                  transition: "color 0.2s",
                }}
              >
                {link.name}
              </Link>
            ))}
          </nav>

          {/* Right side */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-end",
              gap: "0.6rem",
            }}
          >
            <button
              onClick={toggle}
              aria-label={themeLabel}
              title={themeLabel}
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: "38px",
                height: "38px",
                borderRadius: "0.5rem",
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--muted)",
                cursor: "pointer",
                flexShrink: 0,
              }}
            >
              {effective === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <Link to="/scan" className="hidden md:block" style={ctaStyle}>
              Scan your agent
            </Link>
            <button
              className="md:hidden"
              aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              style={{
                padding: "0.5rem",
                background: "none",
                border: "none",
                color: "var(--text)",
                cursor: "pointer",
              }}
            >
              {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <div
            className="md:hidden"
            style={{
              paddingTop: "1rem",
              borderTop: "1px solid var(--border)",
              marginTop: "1rem",
            }}
          >
            <nav style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.name}
                  to={link.href}
                  onClick={() => setMobileMenuOpen(false)}
                  style={{
                    fontSize: "0.875rem",
                    fontWeight: "500",
                    color:
                      location.pathname === link.href
                        ? "var(--pink-ink)"
                        : "var(--text)",
                    textDecoration: "none",
                  }}
                >
                  {link.name}
                </Link>
              ))}
              <Link
                to="/scan"
                onClick={() => setMobileMenuOpen(false)}
                style={{ ...ctaStyle, padding: "0.75rem", textAlign: "center" }}
              >
                Scan your agent
              </Link>
            </nav>
          </div>
        )}
      </div>
    </header>
  );
}
