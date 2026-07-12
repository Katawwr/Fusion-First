import React from 'react';

const variants = {
  primary: 'bg-fusion-pink-gradient text-white shadow-lg hover:shadow-xl hover:opacity-90',
  secondary: 'bg-surface border border-app-border text-app-text hover:bg-surface-2',
  ghost: 'bg-transparent text-fusion-cyan hover:bg-fusion-purple-light',
  outline: 'bg-transparent border border-fusion-cyan text-fusion-cyan hover:bg-fusion-cyan hover:text-fusion-purple',
};

const sizes = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-5 py-2.5 text-base',
  lg: 'px-8 py-3 text-lg',
};

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  onClick,
  className = '',
  type = 'button',
  ...props
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`
        ${variants[variant]}
        ${sizes[size]}
        rounded-lg font-medium
        transition-all duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
        cursor-pointer
        ${className}
      `}
      {...props}
    >
      {children}
    </button>
  );
}
