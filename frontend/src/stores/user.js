import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiFetch } from '../api/client.js'

const USER_KEY = 'tutorloop_user'
const TOKEN_KEY = 'tutorloop_token'

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

export const useUserStore = defineStore('user', () => {
  const token = ref(loadJson(TOKEN_KEY, ''))
  const user = ref(loadJson(USER_KEY, null))
  const isLoggedIn = computed(() => Boolean(token.value && user.value?.id && !isTokenExpired(token.value)))

  function setAuth(newToken, newUser) {
    token.value = newToken
    user.value = newUser
    try {
      localStorage.setItem(TOKEN_KEY, JSON.stringify(newToken))
      localStorage.setItem(USER_KEY, JSON.stringify(newUser))
    } catch {
      // ignore
    }
  }

  function clearAuth() {
    token.value = ''
    user.value = null
    try {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    } catch {
      // ignore
    }
  }

  async function fetchProfile() {
    if (!token.value) return
    // Don't attempt to fetch if the token is already expired.
    if (isTokenExpired(token.value)) {
      clearAuth()
      return
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
    user,
    isLoggedIn,
    userId: computed(() => user.value?.id || ''),
    userRole: computed(() => user.value?.role || ''),
    isAdmin: computed(() => user.value?.role === 'admin'),
    isTeacher: computed(() => user.value?.role === 'teacher' || user.value?.role === 'admin'),
    setAuth,
    clearAuth,
    fetchProfile
  }
})
