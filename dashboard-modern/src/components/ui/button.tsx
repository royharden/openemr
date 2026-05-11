import type { ButtonHTMLAttributes } from 'react'

type Variant = 'default' | 'secondary' | 'ghost' | 'danger'

const VARIANTS: Record<Variant, string> = {
  default: 'bg-neutral-900 text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200',
  secondary: 'bg-neutral-100 text-neutral-900 hover:bg-neutral-200 dark:bg-neutral-800 dark:text-neutral-100 dark:hover:bg-neutral-700',
  ghost: 'bg-transparent hover:bg-neutral-100 dark:hover:bg-neutral-800',
  danger: 'bg-red-600 text-white hover:bg-red-700',
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & Readonly<{ variant?: Variant }>

export function Button({ className, variant = 'default', type = 'button', ...rest }: Props) {
  const classes = [
    'inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
    'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500',
    'disabled:pointer-events-none disabled:opacity-50',
    VARIANTS[variant],
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return <button type={type} className={classes} {...rest} />
}
