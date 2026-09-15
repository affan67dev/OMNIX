import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { ErrorTracker } from './components/ErrorTracker'
import './index.css'

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled startup rejection', event.reason)
  event.preventDefault()
})

window.addEventListener('error', (event) => {
  console.error('Unhandled startup error', event.error ?? event.message)
})

try {
  const root = document.getElementById('root')
  if (!root) {
    throw new Error('Root container not found')
  }
  createRoot(root).render(
    <StrictMode>
      <ErrorTracker>
        <App />
      </ErrorTracker>
    </StrictMode>,
  )
} catch (error) {
  console.error('Fatal startup render failure', error)
  const fallbackRoot = document.getElementById('root')
  if (fallbackRoot) {
    fallbackRoot.innerHTML = '<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#ffffff;color:#0f172a;font-family:sans-serif;padding:20px;text-align:center;"><div><strong>OMNIX could not initialize.</strong><br>Please reload the application.</div></div>'
  }
}
