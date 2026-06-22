import { useUserStore } from '../stores/user.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const DEFAULT_TIMEOUT_MS = 30000

function buildUrl(path) {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE}${normalized}`
}

function mergeHeaders(options, token) {
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...options.headers
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    return response.text()
  }

  const text = await response.text().catch(() => '')
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch (err) {
    err.message = `JSON 解析失败：${err.message}`
    err.raw = text
    throw err
  }
}

export async function apiFetch(path, options = {}) {
  const userStore = useUserStore()
  const url = buildUrl(path)
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS

  const controller = new AbortController()
  const timeoutId = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: mergeHeaders(options, userStore.token)
    })

    if (timeoutId) clearTimeout(timeoutId)

    if (response.status === 401) {
      userStore.clearAuth()
      const err = new Error('登录已过期，请重新登录')
      err.code = 'UNAUTHORIZED'
      err.status = 401
      throw err
    }

    if (!response.ok) {
      const body = await response.text().catch(() => '')
      const err = new Error(`请求失败：${response.status} ${body}`)
      err.status = response.status
      err.code = `HTTP_${response.status}`
      throw err
    }

    return await parseResponse(response)
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId)

    if (err.name === 'AbortError') {
      const aborted = new Error(timeoutMs > 0 ? '请求超时，请稍后重试' : '请求已取消')
      aborted.code = 'ABORTED'
      aborted.isAbort = true
      throw aborted
    }

    if (err.name === 'TypeError' || err.message?.includes('fetch')) {
      const networkErr = new Error('网络异常，请检查网络连接')
      networkErr.code = 'NETWORK_ERROR'
      networkErr.original = err
      throw networkErr
    }

    throw err
  }
}
