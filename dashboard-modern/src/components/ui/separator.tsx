import type { HTMLAttributes } from 'react'

type Props = HTMLAttributes<HTMLDivElement> & Readonly<{ orientation?: 'horizontal' | 'vertical' }>

export function Separator({ className, orientation = 'horizontal', ...rest }: Props) {
  const dim = orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px'
  const classes = ['shrink-0 bg-neutral-200 dark:bg-neutral-800', dim, className].filter(Boolean).join(' ')
  return <div role="separator" aria-orientation={orientation} className={classes} {...rest} />
}
