import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from '@/App'
import '@/styles/tailwind.css'

async function bootstrap() {
  // Optional MSW boot for `start:mock` and tests-in-browser. The handler
  // bundle is tree-shaken out of `start:live` builds because the `if`
  // is statically false at build time when VITE_USE_MSW=0.
  if (import.meta.env.VITE_USE_MSW === '1') {
    const { startWorker } = await import('@/test/msw/browser')
    await startWorker()
  }

  const root = document.getElementById('root')
  if (root == null) {
    throw new Error('main.tsx: #root element missing from index.html')
  }

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
    },
  })

  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  )
}

void bootstrap()
