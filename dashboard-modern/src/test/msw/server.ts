import { setupServer } from 'msw/node'
import { handlers } from './handlers'

/**
 * MSW Node server used by Vitest.
 *
 * Lifecycle is wired in src/test/setup.ts via beforeAll/afterAll/afterEach.
 * Individual test files that need a fresh handler override can call
 * server.use(...) inside a test and it will be reset by afterEach.
 *
 * onUnhandledRequest is set to 'error' in setup.ts so that any fetch the
 * SPA makes that isn't covered by a handler fails loudly — preventing
 * silent fixture-miss bugs.
 */
export const server = setupServer(...handlers)
