import { createApp } from 'vue'
import { createPinia } from 'pinia'
import * as Sentry from '@sentry/vue'
import App from './App.vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import router from './router'

const app = createApp(App)
app.component('ErrorBoundary', ErrorBoundary)

if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    app,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    integrations: [
      Sentry.browserTracingIntegration({ router }),
      Sentry.replayIntegration({ maskAllText: true, blockAllMedia: true })
    ],
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0.0,
    replaysOnErrorSampleRate: 0.1
  })
}

// Catch unhandled promise rejections so they don't silently disappear.
// This covers fetch/abort failures in async code paths that lack try/catch.
window.addEventListener('unhandledrejection', (event) => {
  // AbortErrors from cancelled fetches (e.g. navigating away mid-request)
  // are expected and should not be reported.
  if (event.reason?.name === 'AbortError') {
    event.preventDefault()
    return
  }
  console.error('Unhandled promise rejection:', event.reason)
  if (import.meta.env.VITE_SENTRY_DSN) {
    Sentry.captureException(event.reason)
  }
})

app.use(createPinia())
app.use(router)

app.mount('#app')
