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
  // <form> 裡沒指定 type 的 button 預設是 submit，會讓「Auto layout」「Delete」
  // 這種純操作按鈕意外送出表單。需要送出的地方都有自己寫 type="submit"。
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
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
