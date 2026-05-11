import { useState } from 'react'
import type { ReactNode } from 'react'

/**
 * Minimal tooltip primitive — keyboard-and-pointer triggered, no portal
 * (good enough for dashboard chips and code-display). A future
 * iteration can swap in @radix-ui/react-tooltip without touching the
 * call sites.
 */
export function Tooltip({ content, children }: Readonly<{ content: ReactNode; children: ReactNode }>) {
  const [open, setOpen] = useState(false)
  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <span
          role="tooltip"
          className="pointer-events-none absolute z-50 left-1/2 top-full -translate-x-1/2 mt-1 whitespace-nowrap rounded bg-neutral-900 px-2 py-1 text-xs text-white shadow"
        >
          {content}
        </span>
      )}
    </span>
  )
}
