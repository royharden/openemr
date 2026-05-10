import { setupServer } from 'msw/node'
import { handlers } from './handlers'

/**
 * MSW Node server used by Vitest. Workstream D wires the
 * beforeAll/afterAll/afterEach lifecycle in src/test/setup.ts.
 */
export const server = setupServer(...handlers)
