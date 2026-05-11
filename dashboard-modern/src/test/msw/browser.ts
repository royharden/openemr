import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

/**
 * Browser-side MSW worker used by `npm run start:mock` (set via
 * VITE_USE_MSW=1). main.tsx imports this lazily so live builds tree-
 * shake the handlers out.
 *
 * Dev-time prerequisite: `npx msw init public --save` writes
 * `public/mockServiceWorker.js`. Workstream D may automate this in a
 * postinstall step.
 */
const worker = setupWorker(...handlers)

export async function startWorker(): Promise<void> {
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}
