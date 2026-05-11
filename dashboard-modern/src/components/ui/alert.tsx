import type { HTMLAttributes } from 'react'

type Tone = 'default' | 'info' | 'warning' | 'error' | 'success'

const TONES: Record<Tone, string> = {
  default: 'border-neutral-200 bg-white text-neutral-900 dark:border-neutral-800 dark:bg-neutral-950 dark:text-neutral-100',
  info: 'border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100',
  warning: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100',
  error: 'border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-100',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100',
}

type Props = HTMLAttributes<HTMLDivElement> & Readonly<{ tone?: Tone }>

export function Alert({ className, tone = 'default', ...rest }: Props) {
  const classes = ['relative w-full rounded-lg border p-4 text-sm', TONES[tone], className].filter(Boolean).join(' ')
  return <div className={classes} {...rest} />
}
