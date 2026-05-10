import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Launch } from '@/routes/Launch'
import '@/styles/tailwind.css'

const root = document.getElementById('launch-root')
if (root == null) {
  throw new Error('launch.tsx: #launch-root element missing from launch.html')
}

createRoot(root).render(
  <StrictMode>
    <Launch />
  </StrictMode>,
)
