import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ErrorBoundary } from 'react-error-boundary'
import { LoadingSkeleton } from '@/components/states/LoadingSkeleton'
import { ErrorState } from '@/components/states/ErrorState'

const Launch = lazy(() => import('@/routes/Launch').then((m) => ({ default: m.Launch })))
const Callback = lazy(() => import('@/routes/Callback').then((m) => ({ default: m.Callback })))
const Dashboard = lazy(() => import('@/routes/Dashboard').then((m) => ({ default: m.Dashboard })))

export function App() {
  return (
    <ErrorBoundary fallbackRender={({ error }) => <ErrorState error={error as Error} />}>
      <BrowserRouter>
        <Suspense fallback={<LoadingSkeleton label="Loading…" />}>
          <Routes>
            <Route path="/launch" element={<Launch />} />
            <Route path="/launch.html" element={<Launch />} />
            <Route path="/callback" element={<Callback />} />
            <Route path="/index.html" element={<Callback />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route
              path="*"
              element={
                <ErrorState
                  title="Page not found"
                  error={new Error('The requested route does not exist.')}
                />
              }
            />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
