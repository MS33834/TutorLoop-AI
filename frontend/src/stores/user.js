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

export const useUserStore = defineStore('user', () => {
  const token = ref(loadJson(TOKEN_KEY, ''))
  const user = ref(loadJson(USER_KEY, null))
  const isLoggedIn = computed(() => Boolean(token.value && user.value?.id))

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
    try {
      const profile = await apiFetch('/api/auth/me')
      user.value = profile
      try {
        localStorage.setItem(USER_KEY, JSON.stringify(profile))
      } catch {
        // ignore
      }
    } catch {
      clearAuth()
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
    setAuth,
    clearAuth,
    fetchProfile
  }
})
