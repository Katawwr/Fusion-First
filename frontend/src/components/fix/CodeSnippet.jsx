import React from "react";
import CopyButton from "../ui/CopyButton";

// Monospace code block with a copy button. Used for the hardened prompt and the runtime snippet.
export default function CodeSnippet({
  code,
  language = "",
  copyLabel = "Copy",
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-app-border bg-surface-2">
      <div className="flex items-center justify-between border-b border-app-border px-3 py-1.5">
        <span className="font-mono text-xs uppercase tracking-wide text-app-subtle">
          {language || "text"}
        </span>
        <CopyButton text={code} label={copyLabel} />
      </div>
      <pre className="max-h-96 overflow-auto p-3 text-xs leading-relaxed text-app-text">
        <code>{code}</code>
      </pre>
    </div>
  );
}
