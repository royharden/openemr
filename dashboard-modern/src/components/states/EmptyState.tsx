type Props = Readonly<{
  title?: string
  description?: string
}>

export function EmptyState({ title = 'Nothing to show', description }: Props) {
  return (
    <div className="text-sm text-neutral-500 italic">
      <span className="font-medium not-italic">{title}</span>
      {description != null && <span className="ml-1">— {description}</span>}
    </div>
  )
}
