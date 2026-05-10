import type { HTMLAttributes } from 'react'

type Variant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'outline'

const VARIANTS: Record<Variant, string> = {
  default: 'bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100',
  success: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100',
  warning: 'bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100',
  danger: 'bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100',
  info: 'bg-sky-100 text-sky-900 dark:bg-sky-900 dark:text-sky-100',
  outline: 'border border-neutral-300 text-neutral-900 dark:border-neutral-700 dark:text-neutral-100',
}

type Props = HTMLAttributes<HTMLSpanElement> & Readonly<{ variant?: Variant }>

export function Badge({ className, variant = 'default', ...rest }: Props) {
  const classes = ['inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium', VARIANTS[variant], className]
    .filter(Boolean)
    .join(' ')
  return <span className={classes} {...rest} />
}
