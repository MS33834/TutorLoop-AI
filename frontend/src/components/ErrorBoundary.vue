<script setup>
import { ref, onErrorCaptured } from 'vue'
import * as Sentry from '@sentry/vue'

const hasError = ref(false)
const errorMessage = ref('')
const errorInfo = ref('')

onErrorCaptured((err, instance, info) => {
  hasError.value = true
  errorMessage.value = err?.message || String(err)
  errorInfo.value = info
  console.error('ErrorBoundary caught:', err, info)
  if (import.meta.env.VITE_SENTRY_DSN) {
    Sentry.captureException(err, { extra: { vueErrorInfo: info } })
  }
  return false
})

function reload() {
  window.location.reload()
}

async function copyError() {
  const text = `${errorMessage.value}\n${errorInfo.value}`
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // ignore
  }
}
</script>

<template>
  <div v-if="hasError" class="error-boundary">
    <div class="error-card">
      <h2 class="error-title">页面出现了一点问题</h2>
      <p class="error-desc">我们已经记录了错误信息，请刷新页面重试。</p>
      <details class="error-details">
        <summary>查看错误详情（用于反馈）</summary>
        <pre class="error-code">{{ errorMessage }}
{{ errorInfo }}</pre>
        <button class="copy-btn" type="button" @click="copyError">复制错误信息</button>
      </details>
      <button class="error-btn" type="button" @click="reload">刷新页面</button>
    </div>
  </div>
  <slot v-else />
</template>

<style scoped>
.error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  padding: 1rem;
}

.error-card {
  max-width: 28rem;
  width: 100%;
  text-align: center;
  padding: 1.5rem;
  background: #ffffff;
  border: 1px solid #fee2e2;
  border-radius: 0.875rem;
}

.error-title {
  margin: 0 0 0.5rem;
  color: #b91c1c;
  font-size: 1.125rem;
}

.error-desc {
  margin: 0 0 1rem;
  color: #6b7280;
  font-size: 0.9375rem;
}

.error-details {
  margin-bottom: 1rem;
  text-align: left;
  font-size: 0.875rem;
  color: #4b5563;
}

.error-code {
  margin: 0.5rem 0;
  padding: 0.75rem;
  background: #f9fafb;
  border-radius: 0.5rem;
  font-size: 0.75rem;
  word-break: break-word;
  white-space: pre-wrap;
}

.copy-btn {
  padding: 0.375rem 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #ffffff;
  color: #374151;
  font-size: 0.8125rem;
  cursor: pointer;
}

.error-btn {
  padding: 0.5rem 1.25rem;
  background: #2563eb;
  color: #ffffff;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-size: 0.9375rem;
}
</style>
