import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import router from './router'

const app = createApp(App)
app.component('ErrorBoundary', ErrorBoundary)

// Lazy-load Sentry only when a DSN is configured so builds without Sentry
// don't ship the (~80KB) SDK as dead code.
let Sentry = null
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry = await import('@sentry/vue')
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
  if (Sentry) {
    Sentry.captureException(event.reason)
  }
  // 抑制浏览器默认的 "Uncaught (in promise)" 控制台告警：上面已记录并上报，
  // 再让默认行为触发会造成重复日志，干扰排查。
  event.preventDefault()
})

// 注册 Service Worker（PWA）。vite-plugin-pwa 以 autoUpdate 模式生成 SW，
// 但需要显式导入 virtual:pwa-register 才会真正注册。用动态 import + catch
// 包裹，确保即便 SW 注册失败也不会阻塞应用启动。
if ('serviceWorker' in navigator) {
  import('virtual:pwa-register')
    .then(({ registerSW }) => {
      registerSW({
        onNeedRefresh() {
          showUpdateToast()
        },
        onRegisterError(err) {
          console.warn('Service Worker 注册失败:', err)
        }
      })
    })
    .catch((err) => {
      // 开发环境或插件未启用时模块解析失败，忽略即可。
      console.warn('Service Worker 模块加载失败:', err)
    })
}

// 新版本可用时弹出轻量提示，引导用户刷新获取最新内容。
function showUpdateToast() {
  if (document.getElementById('pwa-update-toast')) return
  const toast = document.createElement('div')
  toast.id = 'pwa-update-toast'
  toast.setAttribute('role', 'alert')
  toast.textContent = '发现新版本，刷新即可更新。'
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.textContent = '刷新'
  btn.addEventListener('click', () => {
    toast.remove()
    window.location.reload()
  })
  toast.appendChild(btn)
  Object.assign(toast.style, {
    position: 'fixed',
    left: '50%',
    bottom: '1rem',
    transform: 'translateX(-50%)',
    zIndex: '9999',
    display: 'flex',
    alignItems: 'center',
    gap: '0.625rem',
    padding: '0.625rem 1rem',
    background: '#1f2937',
    color: '#ffffff',
    fontSize: '0.875rem',
    borderRadius: '0.625rem',
    boxShadow: '0 8px 24px rgba(0,0,0,0.2)'
  })
  Object.assign(btn.style, {
    padding: '0.25rem 0.75rem',
    border: 'none',
    borderRadius: '0.375rem',
    background: '#2563eb',
    color: '#ffffff',
    fontSize: '0.8125rem',
    cursor: 'pointer'
  })
  document.body.appendChild(toast)
}

app.use(createPinia())
app.use(router)

app.mount('#app')
