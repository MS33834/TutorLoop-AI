import { useUserStore } from '../stores/user.js'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const DEFAULT_TIMEOUT_MS = 30000
const MAX_RETRIES = 2
const RETRY_BASE_DELAY_MS = 500

// In-flight GET request dedup: key by URL, value is the shared promise.
const _inflightGets = new Map()

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

function isRetryableError(err, response) {
  // Network errors and 5xx responses are worth retrying.
  if (err.code === 'NETWORK_ERROR') return true
  if (response && response.status >= 500 && response.status < 600) return true
  return false
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Low-level fetch wrapper. On 401 it throws an UNAUTHORIZED error WITHOUT
 * clearing auth — the caller (_apiFetchWithRetry) is responsible for trying
 * a token refresh and retrying before giving up.
 */
async function rawFetch(url, options, token, timeoutMs) {
  const controller = new AbortController()
  const timeoutId = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: mergeHeaders(options, token)
    })

    if (timeoutId) clearTimeout(timeoutId)

    if (response.status === 401) {
      const err = new Error('登录已过期，请重新登录')
      err.code = 'UNAUTHORIZED'
      err.status = 401
      err._response = response
      throw err
    }

    if (!response.ok) {
      const body = await response.text().catch(() => '')
      const err = new Error('请求没能成功，请稍后重试')
      err.status = response.status
      err.code = `HTTP_${response.status}`
      err._response = response
      err._body = body
      throw err
    }

    return await parseResponse(response)
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId)

    if (err.name === 'AbortError') {
      const aborted = new Error(timeoutMs > 0 ? '请求超时了，再试一次看看' : '请求已取消')
      aborted.code = 'ABORTED'
      aborted.isAbort = true
      throw aborted
    }

    if (err.name === 'TypeError' || err.message?.includes('fetch')) {
      const networkErr = new Error('网络好像断开了，请检查后重试')
      networkErr.code = 'NETWORK_ERROR'
      networkErr.original = err
      throw networkErr
    }

    throw err
  }
}

export async function apiFetch(path, options = {}) {
  const userStore = useUserStore()
  const url = buildUrl(path)
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const method = (options.method || 'GET').toUpperCase()

  // Dedup in-flight GET requests: identical URL returns the same promise.
  if (method === 'GET') {
    const existing = _inflightGets.get(url)
    if (existing) return existing

    const promise = _apiFetchWithRetry(url, options, userStore, timeoutMs)
      .finally(() => _inflightGets.delete(url))
    _inflightGets.set(url, promise)
    return promise
  }

  return _apiFetchWithRetry(url, options, userStore, timeoutMs)
}

async function _apiFetchWithRetry(url, options, userStore, timeoutMs) {
  let lastErr = null
  // Whether we've already attempted a token refresh for this request.
  // We only refresh once to avoid infinite loops.
  let refreshed = false

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    // Read the latest token from the store on each attempt so that a
    // refreshed token is picked up after a 401-triggered refresh.
    const token = userStore.token
    try {
      return await rawFetch(url, options, token, timeoutMs)
    } catch (err) {
      lastErr = err

      // On 401, try a silent token refresh once before giving up. If the
      // refresh succeeds, retry the original request with the new token
      // instead of logging the user out.
      if (err.code === 'UNAUTHORIZED') {
        if (!refreshed && userStore.refreshToken) {
          refreshed = true
          const newToken = await userStore.refreshAccessToken()
          if (newToken) {
            // Retry immediately without counting against MAX_RETRIES.
            attempt -= 1
            continue
          }
          // Refresh failed — clear auth and surface the error.
          userStore.clearAuth()
        } else {
          // Already tried refreshing (or no refresh token) — give up.
          userStore.clearAuth()
        }
        throw err
      }

      // Don't retry on aborts.
      if (err.isAbort || err.code === 'ABORTED') {
        throw err
      }

      // Only retry on network errors or 5xx.
      const response = err._response
      if (!isRetryableError(err, response) || attempt >= MAX_RETRIES) {
        // Re-attach body text for non-OK HTTP errors so callers see detail.
        if (err._body) {
          try {
            const parsed = JSON.parse(err._body)
            if (parsed.detail) err.message = parsed.detail
          } catch {
            // keep default message
          }
        }
        throw err
      }

      // Exponential backoff before the next attempt.
      await sleep(RETRY_BASE_DELAY_MS * Math.pow(2, attempt))
    }
  }

  throw lastErr
}
