import React from "react";

const variants = {
  default: "bg-surface border-app-border shadow-soft",
  elevated: "bg-surface border-app-border shadow-card",
  outline: "bg-transparent border-app-border",
};

export default function Card({
  children,
  variant = "default",
  className = "",
  padding = "p-6",
  ...props
}) {
  // Single-line class string: newlines inside className break Tailwind's sibling
  // utilities (space-y-*) on the parent, which silently collapses page spacing.
  return (
    <div
      className={`${variants[variant]} ${padding} border rounded-2xl ${className}`.trim()}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className = "" }) {
  return <div className={`mb-4 ${className}`}>{children}</div>;
}

export function CardTitle({ children, className = "" }) {
  return (
    <h3 className={`text-xl font-semibold text-app-text ${className}`}>
      {children}
    </h3>
  );
}

export function CardDescription({ children, className = "" }) {
  return <p className={`text-app-muted mt-1 ${className}`}>{children}</p>;
}

export function CardContent({ children, className = "" }) {
  return <div className={className}>{children}</div>;
}

export function CardFooter({ children, className = "" }) {
  return (
    <div className={`mt-4 pt-4 border-t border-app-border ${className}`}>
      {children}
    </div>
  );
}
