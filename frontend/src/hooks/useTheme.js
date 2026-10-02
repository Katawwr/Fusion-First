import { useCallback, useEffect, useState } from "react";

// Theme is stored as an explicit 'light' | 'dark' choice, or null to follow the OS preference.
// The choice is written to <html data-theme="…">, which index.css reads; null removes the attribute
// so the prefers-color-scheme rules take over.
const KEY = "fusion-theme";

function stored() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function systemTheme() {
  return typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

export default function useTheme() {
  const [choice, setChoice] = useState(stored); // 'light' | 'dark' | null

  useEffect(() => {
    const root = document.documentElement;
    if (choice === "light" || choice === "dark") {
      root.setAttribute("data-theme", choice);
      try {
        localStorage.setItem(KEY, choice);
      } catch {
        /* ignore */
      }
    } else {
      root.removeAttribute("data-theme");
      try {
        localStorage.removeItem(KEY);
      } catch {
        /* ignore */
      }
    }
  }, [choice]);

  const effective = choice || systemTheme();

  const toggle = useCallback(() => {
    setChoice((c) => ((c || systemTheme()) === "dark" ? "light" : "dark"));
  }, []);

  return { theme: choice, effective, toggle };
}
