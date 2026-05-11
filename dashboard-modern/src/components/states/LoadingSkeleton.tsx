import { Skeleton } from '@/components/ui/skeleton'

type Props = Readonly<{
  label?: string
  rows?: number
}>

export function LoadingSkeleton({ label, rows = 3 }: Props) {
  return (
    <div className="space-y-2" aria-busy="true" aria-live="polite">
      {label != null && <p className="sr-only">{label}</p>}
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-4 w-full" />
      ))}
    </div>
  )
}
