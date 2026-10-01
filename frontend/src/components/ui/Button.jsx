import React from "react";

const variants = {
  primary:
    "bg-primary text-on-primary hover:brightness-110",
  secondary:
    "bg-surface border border-app-border text-app-text hover:bg-surface-2 hover:border-app-border-strong",
  ghost: "bg-transparent text-accent-ink hover:bg-accent-soft",
  outline:
    "bg-transparent border border-fusion-accent text-accent-ink hover:bg-accent-soft",
};

const sizes = {
  sm: "px-3.5 py-1.5 text-sm",
  md: "px-5 py-2.5 text-base",
  lg: "px-7 py-3 text-base",
};

export default function Button({
  children,
  variant = "primary",
  size = "md",
  disabled = false,
  onClick,
  className = "",
  type = "button",
  ...props
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${variants[variant]} ${sizes[size]} rounded-lg font-medium transition-all duration-200 cursor-pointer disabled:cursor-not-allowed disabled:bg-none disabled:bg-surface-2 disabled:text-app-subtle disabled:shadow-none disabled:border-app-border disabled:translate-y-0 ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  );
}
