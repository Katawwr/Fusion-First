import React from 'react';

const variants = {
  default: 'bg-surface-2 text-app-text',
  critical: 'bg-severity-critical text-white',
  high: 'bg-severity-high text-black',
  medium: 'bg-severity-medium text-black',
  low: 'bg-severity-low text-white',
  success: 'bg-green-500 text-white',
  info: 'bg-fusion-cyan text-fusion-purple',
  popular: 'bg-fusion-pink-gradient text-white',
};

const sizes = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-3 py-1 text-sm',
  lg: 'px-4 py-1.5 text-base',
};

export default function Badge({
  children,
  variant = 'default',
  size = 'md',
  className = '',
}) {
  return (
    <span
      className={`
        ${variants[variant]}
        ${sizes[size]}
        inline-flex items-center
        font-medium
        rounded-full
        ${className}
      `}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }) {
  const severityMap = {
    critical: 'CRITICAL',
    high: 'HIGH',
    medium: 'MEDIUM',
    low: 'LOW',
  };

  return (
    <Badge variant={severity} size="sm">
      {severityMap[severity] || severity.toUpperCase()}
    </Badge>
  );
}
