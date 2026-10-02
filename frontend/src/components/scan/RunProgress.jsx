import React from "react";

export default function RunProgress({ completed, total, message }) {
  const pctDone = total ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between text-sm text-app-muted">
        <span>{message || "Starting…"}</span>
        <span className="font-mono text-app-muted">
          {completed}/{total || "…"}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent transition-all duration-300"
          style={{ width: `${pctDone}%` }}
        />
      </div>
    </div>
  );
}
