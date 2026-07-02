import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { API_BASE, apiFetch } from '../api/client.js'

const USER_KEY = 'tutorloop_user'
// The access token is held in memory only (Pinia state) so it cannot be
// stolen via XSS from localStorage. The refresh token lives in an HttpOnly
// cookie set by the backend, so it is never touched by JS.

function loadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

/**
 * Decode a JWT payload without verifying (client-side expiry check only).
 * Returns null if the token is malformed. Uses TextDecoder for UTF-8 safety.
 */
function decodeJwtPayload(token) {
  if (!token || typeof token !== 'string') return null
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    // Handle UTF-8 multi-byte characters (e.g. non-ASCII usernames) correctly.
    const binary = atob(payload)
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0))
    const json = new TextDecoder().decode(bytes)
    return JSON.parse(json)
  } catch {
    return null
  }
}

function isTokenExpired(token) {
  const payload = decodeJwtPayload(token)
  // A malformed token or one without an expiry must be treated as expired
  // for security — never trust a token we cannot verify.
  if (!payload || !payload.exp) return true
  // Treat tokens expiring within the next 30 seconds as expired to avoid
  // race conditions where the token expires mid-request.
  return payload.exp * 1000 <= Date.now() + 30000
}

// Singleton promise to avoid concurrent refresh calls.
let _refreshPromise = null

export const useUserStore = defineStore('user', () => {
  // Access token lives in memory only; it is NOT persisted to localStorage.
  const token = ref('')
  const user = ref(loadJson(USER_KEY, null))
  const isLoggedIn = computed(() => Boolean(token.value && user.value?.id && !isTokenExpired(token.value)))

  function setAuth(newToken, _newRefreshToken, newUser) {
    // The refresh token is set as an HttpOnly cookie by the backend; we do
    // not store it. _newRefreshToken is accepted for backward compat but
    // intentionally ignored.
    token.value = newToken
    user.value = newUser
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(newUser))
    } catch {
      // ignore
    }
  }

  function clearAuth() {
    token.value = ''
    user.value = null
    try {
      localStorage.removeItem(USER_KEY)
    } catch {
      // ignore
    }
    _refreshPromise = null
  }

  /**
   * Silently refresh the access token using the HttpOnly refresh cookie.
   * Returns the new access token, or null if refresh failed.
   * Concurrent calls share the same promise to avoid duplicate requests.
   */
  async function refreshAccessToken() {
    // Reuse an in-flight refresh to avoid duplicate calls.
    if (_refreshPromise) return _refreshPromise

    _refreshPromise = (async () => {
      try {
        // credentials: 'include' is required so the HttpOnly refresh cookie
        // is sent. No body needed — the backend reads the cookie.
        const res = await fetch(`${API_BASE}/api/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' }
        })
        if (!res.ok) {
          // Refresh cookie invalid/expired — log out.
          clearAuth()
          return null
        }
        const data = await res.json()
        token.value = data.access_token
        return data.access_token
      } catch {
        // Network error — don't clear auth, just fail this refresh.
        return null
      } finally {
        _refreshPromise = null
      }
    })()

    return _refreshPromise
  }

  async function logout() {
    try {
      // Tell the backend to clear the refresh cookie.
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      })
    } catch {
      // ignore network errors on logout
    }
    clearAuth()
  }

  async function fetchProfile() {
    // 无 token 时直接短路返回，避免无谓的 401 请求。
    if (!token.value) return
    // If the access token is expired, try to refresh silently via the cookie.
    if (isTokenExpired(token.value)) {
      const newToken = await refreshAccessToken()
      if (!newToken) {
        clearAuth()
        return
      }
    }
    try {
      const profile = await apiFetch('/api/auth/me')
      user.value = profile
      try {
        localStorage.setItem(USER_KEY, JSON.stringify(profile))
      } catch {
        // ignore
      }
    } catch (err) {
      // Only clear auth on actual auth failures (401/403), not on network
      // errors or server failures — those shouldn't log the user out.
      if (err.code === 'UNAUTHORIZED' || err.code === 'HTTP_403') {
        clearAuth()
      }
    }
  }

  return {
    token,
    user,
    isLoggedIn,
    userId: computed(() => user.value?.id || ''),
    userRole: computed(() => user.value?.role || ''),
    isAdmin: computed(() => user.value?.role === 'admin'),
    isTeacher: computed(() => user.value?.role === 'teacher' || user.value?.role === 'admin'),
    setAuth,
    clearAuth,
    logout,
    fetchProfile,
    refreshAccessToken
  }
})
