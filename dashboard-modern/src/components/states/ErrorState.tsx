import { Alert } from '@/components/ui/alert'

type Props = Readonly<{
  title?: string
  error: Error
}>

export function ErrorState({ title = 'Something went wrong', error }: Props) {
  return (
    <Alert role="alert" tone="error">
      <p className="font-medium">{title}</p>
      <p className="text-sm opacity-80">{error.message}</p>
    </Alert>
  )
}
