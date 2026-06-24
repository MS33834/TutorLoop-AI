import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiFetch } from '../api/client.js'

const USER_KEY = 'tutorloop_user'
const TOKEN_KEY = 'tutorloop_token'
const REFRESH_TOKEN_KEY = 'tutorloop_refresh_token'

function loadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

function loadStr(key, fallback = '') {
  try {
    return localStorage.getItem(key) || fallback
  } catch {
    return fallback
  }
}

/**
 * Decode a JWT payload without verifying (client-side expiry check only).
 * Returns null if the token is malformed.
 */
function decodeJwtPayload(token) {
  if (!token || typeof token !== 'string') return null
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const json = atob(payload)
    return JSON.parse(json)
  } catch {
    return null
  }
}

function isTokenExpired(token) {
  const payload = decodeJwtPayload(token)
  if (!payload || !payload.exp) return false
  // Treat tokens expiring within the next 30 seconds as expired to avoid
  // race conditions where the token expires mid-request.
  return payload.exp * 1000 <= Date.now() + 30000
}

// Singleton promise to avoid concurrent refresh calls.
let _refreshPromise = null

export const useUserStore = defineStore('user', () => {
  const token = ref(loadStr(TOKEN_KEY))
  const refreshToken = ref(loadStr(REFRESH_TOKEN_KEY))
  const user = ref(loadJson(USER_KEY, null))
  const isLoggedIn = computed(() => Boolean(token.value && user.value?.id && !isTokenExpired(token.value)))

  function setAuth(newToken, newRefreshToken, newUser) {
    token.value = newToken
    refreshToken.value = newRefreshToken
    user.value = newUser
    try {
      localStorage.setItem(TOKEN_KEY, newToken)
      localStorage.setItem(REFRESH_TOKEN_KEY, newRefreshToken)
      localStorage.setItem(USER_KEY, JSON.stringify(newUser))
    } catch {
      // ignore
    }
  }

  function clearAuth() {
    token.value = ''
    refreshToken.value = ''
    user.value = null
    try {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    } catch {
      // ignore
    }
    _refreshPromise = null
  }

  /**
   * Silently refresh the access token using the stored refresh token.
   * Returns the new access token, or null if refresh failed.
   * Concurrent calls share the same promise to avoid duplicate requests.
   */
  async function refreshAccessToken() {
    if (!refreshToken.value) return null
    // Reuse an in-flight refresh to avoid duplicate calls.
    if (_refreshPromise) return _refreshPromise

    _refreshPromise = (async () => {
      try {
        const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
        const res = await fetch(`${API_BASE}/api/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken.value })
        })
        if (!res.ok) {
          // Refresh token invalid/expired — log out.
          clearAuth()
          return null
        }
        const data = await res.json()
        token.value = data.access_token
        refreshToken.value = data.refresh_token
        try {
          localStorage.setItem(TOKEN_KEY, data.access_token)
          localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
        } catch {
          // ignore
        }
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

  async function fetchProfile() {
    if (!token.value) return
    // If the access token is expired but we have a refresh token, try to
    // refresh silently before fetching the profile.
    if (isTokenExpired(token.value)) {
      if (refreshToken.value) {
        const newToken = await refreshAccessToken()
        if (!newToken) {
          clearAuth()
          return
        }
      } else {
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
      // Only clear auth on 401/403 (actual auth failures), not on network
      // errors or server failures — those shouldn't log the user out.
      if (err.code === 'UNAUTHORIZED' || err.status === 403) {
        clearAuth()
      }
    }
  }

  // Restore legacy user_id if present, then migrate to new auth
  const legacyId = localStorage.getItem('tutorloop_user_id')
  if (legacyId && !isLoggedIn.value) {
    try {
      localStorage.removeItem('tutorloop_user_id')
    } catch {
      // ignore
    }
  }

  return {
    token,
    refreshToken,
    user,
    isLoggedIn,
    userId: computed(() => user.value?.id || ''),
    userRole: computed(() => user.value?.role || ''),
    isAdmin: computed(() => user.value?.role === 'admin'),
    isTeacher: computed(() => user.value?.role === 'teacher' || user.value?.role === 'admin'),
    setAuth,
    clearAuth,
    fetchProfile,
    refreshAccessToken
  }
})
