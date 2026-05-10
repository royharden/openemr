import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { render, type RenderOptions, type RenderResult } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'

/**
 * `renderWithProviders(ui)` — wraps a component with the same providers
 * the real app has, but with isolated stubs (memory router, fresh
 * QueryClient with retry off so failed queries fail fast in tests).
 */
export function renderWithProviders(
  ui: ReactElement,
  { initialEntries = ['/'], ...options }: { initialEntries?: string[] } & Omit<RenderOptions, 'wrapper'> = {},
): RenderResult {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  const Wrapper = ({ children }: Readonly<{ children: ReactNode }>) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
    </QueryClientProvider>
  )

  return render(ui, { wrapper: Wrapper, ...options })
}
