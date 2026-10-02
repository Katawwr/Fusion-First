import React, { useState } from "react";
import { Check, Copy } from "lucide-react";

export default function CopyButton({ text, label = "Copy", className = "" }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Older or insecure contexts.
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  return (
    <button
      type="button"
      onClick={copy}
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.45rem",
        borderRadius: "0.75rem",
        border: `1px solid ${copied ? "var(--accent)" : "var(--border)"}`,
        background: copied ? "var(--accent-soft)" : "var(--surface-2)",
        padding: "0.5rem 0.9rem",
        fontSize: "0.875rem",
        fontWeight: 600,
        color: copied ? "var(--accent-ink)" : "var(--text)",
        cursor: "pointer",
        transition: "all .18s ease",
      }}
    >
      {copied ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />}
      {copied ? "Copied" : label}
    </button>
  );
}
