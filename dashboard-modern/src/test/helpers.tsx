import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { render, type RenderOptions, type RenderResult } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import type { RequestHandler } from 'msw'
import { server } from './msw/server'

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
}

type ProviderOptions = Readonly<{
  initialEntries?: string[]
  queryClient?: QueryClient
}> &
  Omit<RenderOptions, 'wrapper'>

/**
 * `renderWithProviders(ui)` — wraps a component with the same providers
 * the real app has: isolated MemoryRouter + fresh QueryClient with retry
 * off so failed queries fail fast in tests.
 */
export function renderWithProviders(
  ui: ReactElement,
  { initialEntries = ['/'], queryClient, ...options }: ProviderOptions = {},
): RenderResult {
  const client = queryClient ?? createTestQueryClient()

  const Wrapper = ({ children }: Readonly<{ children: ReactNode }>) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
    </QueryClientProvider>
  )

  return render(ui, { wrapper: Wrapper, ...options })
}

/**
 * `renderWithServer(ui, handlers)` — same as `renderWithProviders` but also
 * pushes temporary MSW handler overrides for the duration of this render.
 * Overrides are automatically reset by the `afterEach` in src/test/setup.ts.
 */
export function renderWithServer(
  ui: ReactElement,
  handlers: ReadonlyArray<RequestHandler>,
  options: ProviderOptions = {},
): RenderResult {
  server.use(...handlers)
  return renderWithProviders(ui, options)
}
