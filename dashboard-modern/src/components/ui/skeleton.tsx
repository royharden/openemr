import type { HTMLAttributes } from 'react'

export function Skeleton({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  const classes = ['animate-pulse rounded-md bg-neutral-200 dark:bg-neutral-800', className].filter(Boolean).join(' ')
  return <div className={classes} {...rest} />
}
