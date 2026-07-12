import React from 'react';

// Demo (instant, keyless) vs Real (your prompt, real model) segmented control.
export default function ModeSwitch({ mode, onChange, liveAvailable }) {
  const opt = (value, title, subtitle, disabled) => {
    const active = mode === value;
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange(value)}
        className={`flex-1 rounded-lg px-4 py-2 text-left transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
          active ? 'bg-fusion-pink-gradient text-app-text shadow' : 'bg-app-elev text-app-muted hover:bg-surface-2'
        }`}
      >
        <span className="block text-sm font-semibold">{title}</span>
        <span className="block text-xs opacity-80">{subtitle}</span>
      </button>
    );
  };
  return (
    <div className="flex gap-2">
      {opt('demo', 'Demo scan', 'Instant, no signup')}
      {opt(
        'live',
        'Real scan',
        liveAvailable ? 'Your prompt, real model' : 'Coming soon',
        !liveAvailable
      )}
    </div>
  );
}
