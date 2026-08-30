import { useEffect, useRef, useState } from "react";

/**
 * Fail-safe scroll reveal.
 *
 * The old per-section IntersectionObserver left content at opacity:0 whenever the
 * callback never fired (already-in-view on load, prerender, reduced motion, or a
 * screenshot/crawler), which silently blanked whole sections. This hook:
 *   - reveals immediately if the element is already in view on mount,
 *   - reveals immediately when the user prefers reduced motion,
 *   - and always reveals after a short failsafe timeout.
 * Content is therefore never permanently invisible.
 */
export default function useReveal({ threshold = 0.1, failsafeMs = 600 } = {}) {
  const ref = useRef(null);
  // Start visible when animation is unwanted or unsupported, decided at mount so
  // the effect never has to setState synchronously.
  const [visible, setVisible] = useState(() => {
    if (typeof window === "undefined") return true;
    if (typeof IntersectionObserver === "undefined") return true;
    return !!window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  });

  useEffect(() => {
    if (visible) return undefined;

    const el = ref.current;
    const observer = new IntersectionObserver(
      ([entry]) => entry.isIntersecting && setVisible(true),
      { threshold },
    );
    if (el) observer.observe(el);

    // Failsafe: never leave content permanently hidden (already in view on load,
    // prerender, or an observer that never fires).
    const t = setTimeout(() => setVisible(true), failsafeMs);
    return () => {
      observer.disconnect();
      clearTimeout(t);
    };
  }, [threshold, failsafeMs, visible]);

  return [ref, visible];
}
