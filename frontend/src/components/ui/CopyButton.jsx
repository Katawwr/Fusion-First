import React, { useState } from 'react';

// Copy-to-clipboard button with a brief "Copied" confirmation.
export default function CopyButton({ text, label = 'Copy', className = '' }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for older/insecure contexts.
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  return (
    <button
      type="button"
      onClick={copy}
      className={`rounded-md border border-fusion-cyan-medium bg-fusion-purple-light px-3 py-1.5 text-sm font-medium text-app-text transition-colors hover:bg-fusion-purple-medium ${className}`}
    >
      {copied ? '✓ Copied' : label}
    </button>
  );
}
