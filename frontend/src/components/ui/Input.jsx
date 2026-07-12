import React from 'react';

export default function Input({
  type = 'text',
  placeholder,
  value,
  onChange,
  disabled = false,
  error = false,
  className = '',
  ...props
}) {
  return (
    <input
      type={type}
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      disabled={disabled}
      className={`
        w-full
        px-4 py-3
        bg-surface-2
        border ${error ? 'border-fusion-pink' : 'border-fusion-cyan-medium'}
        rounded-lg
        text-app-text
        placeholder:text-app-subtle
        font-mono
        focus:outline-none focus:border-fusion-cyan
        disabled:opacity-50 disabled:cursor-not-allowed
        transition-colors duration-200
        ${className}
      `}
      {...props}
    />
  );
}

export function Textarea({
  placeholder,
  value,
  onChange,
  disabled = false,
  rows = 10,
  className = '',
  ...props
}) {
  return (
    <textarea
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      disabled={disabled}
      rows={rows}
      className={`
        w-full
        px-4 py-3
        bg-surface-2
        border border-fusion-cyan-medium
        rounded-lg
        text-app-text
        placeholder:text-app-subtle
        font-mono
        resize-none
        focus:outline-none focus:border-fusion-cyan
        disabled:opacity-50 disabled:cursor-not-allowed
        transition-colors duration-200
        ${className}
      `}
      {...props}
    />
  );
}
