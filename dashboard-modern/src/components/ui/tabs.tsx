import { createContext, useContext, useId, useState } from 'react'
import type { ReactNode } from 'react'

type Ctx = { value: string; setValue: (v: string) => void; baseId: string }
const TabsContext = createContext<Ctx | null>(null)

export function Tabs({ defaultValue, children, className }: Readonly<{ defaultValue: string; children: ReactNode; className?: string }>) {
  const [value, setValue] = useState(defaultValue)
  const baseId = useId()
  return (
    <TabsContext.Provider value={{ value, setValue, baseId }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ children, className }: Readonly<{ children: ReactNode; className?: string }>) {
  const classes = ['inline-flex items-center gap-1 rounded-md bg-neutral-100 p-1 dark:bg-neutral-800', className].filter(Boolean).join(' ')
  return (
    <div role="tablist" className={classes}>
      {children}
    </div>
  )
}

export function TabsTrigger({ value, children }: Readonly<{ value: string; children: ReactNode }>) {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error('TabsTrigger must be inside <Tabs>')
  const isActive = ctx.value === value
  return (
    <button
      type="button"
      role="tab"
      id={`${ctx.baseId}-${value}-trigger`}
      aria-selected={isActive}
      aria-controls={`${ctx.baseId}-${value}-panel`}
      className={`px-3 py-1.5 text-sm font-medium rounded-sm transition-colors ${
        isActive ? 'bg-white text-neutral-900 shadow-sm dark:bg-neutral-950 dark:text-neutral-100' : 'text-neutral-600 dark:text-neutral-400'
      }`}
      onClick={() => ctx.setValue(value)}
    >
      {children}
    </button>
  )
}

export function TabsContent({ value, children }: Readonly<{ value: string; children: ReactNode }>) {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error('TabsContent must be inside <Tabs>')
  if (ctx.value !== value) return null
  return (
    <div role="tabpanel" id={`${ctx.baseId}-${value}-panel`} aria-labelledby={`${ctx.baseId}-${value}-trigger`} className="mt-2">
      {children}
    </div>
  )
}
