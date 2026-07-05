import React from 'react';

const variants = {
  default: 'bg-fusion-purple-light border-fusion-cyan-light',
  elevated: 'bg-fusion-purple-medium border-fusion-cyan-medium shadow-xl',
  outline: 'bg-transparent border-fusion-cyan',
};

export default function Card({
  children,
  variant = 'default',
  className = '',
  padding = 'p-6',
  ...props
}) {
  return (
    <div
      className={`
        ${variants[variant]}
        ${padding}
        backdrop-blur-lg
        border
        rounded-xl
        ${className}
      `}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className = '' }) {
  return (
    <div className={`mb-4 ${className}`}>
      {children}
    </div>
  );
}

export function CardTitle({ children, className = '' }) {
  return (
    <h3 className={`text-xl font-semibold text-white ${className}`}>
      {children}
    </h3>
  );
}

export function CardDescription({ children, className = '' }) {
  return (
    <p className={`text-gray-300 mt-1 ${className}`}>
      {children}
    </p>
  );
}

export function CardContent({ children, className = '' }) {
  return (
    <div className={className}>
      {children}
    </div>
  );
}

export function CardFooter({ children, className = '' }) {
  return (
    <div className={`mt-4 pt-4 border-t border-fusion-cyan-light ${className}`}>
      {children}
    </div>
  );
}
