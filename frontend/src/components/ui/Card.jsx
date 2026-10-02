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
