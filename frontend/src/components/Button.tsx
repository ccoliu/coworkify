import clsx from 'clsx'
import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:bg-accent-strong',
  secondary:
    'bg-surface text-ink border border-border hover:bg-plane',
  danger:
    'bg-surface text-status-critical border border-border hover:bg-status-critical hover:text-white',
  ghost: 'text-ink-secondary hover:text-ink hover:bg-plane',
}

export function Button({
  variant = 'secondary',
  className,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-plane',
        disabled && 'opacity-50 cursor-not-allowed',
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  )
}
