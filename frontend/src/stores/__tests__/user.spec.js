import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore } from '../user.js'

function makeToken(payload) {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.signature`
}

describe('user store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('stores access token in memory and user in localStorage', () => {
    const store = useUserStore()
    store.setAuth('access-token', 'ignored-refresh', { id: 'u1', name: 'Alice' })

    expect(store.token).toBe('access-token')
    expect(store.user).toEqual({ id: 'u1', name: 'Alice' })
    expect(localStorage.getItem('tutorloop_user')).toBe(
      JSON.stringify({ id: 'u1', name: 'Alice' })
    )
  })

  it('restores user from localStorage on creation', () => {
    localStorage.setItem('tutorloop_user', JSON.stringify({ id: 'u2', name: 'Bob' }))
    const store = useUserStore()
    expect(store.user).toEqual({ id: 'u2', name: 'Bob' })
  })

  it('clearAuth removes token and localStorage user', () => {
    const store = useUserStore()
    store.setAuth('token', null, { id: 'u1' })
    store.clearAuth()

    expect(store.token).toBe('')
    expect(store.user).toBeNull()
    expect(localStorage.getItem('tutorloop_user')).toBeNull()
  })

  it('isLoggedIn is true only with valid unexpired token', () => {
    const store = useUserStore()
    expect(store.isLoggedIn).toBe(false)

    const exp = Math.floor(Date.now() / 1000) + 3600
    store.setAuth(makeToken({ exp }), null, { id: 'u1' })
    expect(store.isLoggedIn).toBe(true)

    const past = Math.floor(Date.now() / 1000) - 10
    store.setAuth(makeToken({ exp: past }), null, { id: 'u1' })
    expect(store.isLoggedIn).toBe(false)
  })

  it('refreshAccessToken calls backend and sets new token', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'new-token' }),
    })

    const store = useUserStore()
    const token = await store.refreshAccessToken()

    expect(token).toBe('new-token')
    expect(store.token).toBe('new-token')
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/auth/refresh',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      })
    )
  })

  it('refreshAccessToken dedups concurrent calls', async () => {
    global.fetch = vi
      .fn()
      .mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ ok: true, json: async () => ({ access_token: 'tok' }) }), 10))
      )

    const store = useUserStore()
    const [a, b] = await Promise.all([
      store.refreshAccessToken(),
      store.refreshAccessToken(),
    ])

    expect(a).toBe('tok')
    expect(b).toBe('tok')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('logout clears auth after calling backend', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true })
    const store = useUserStore()
    store.setAuth('token', null, { id: 'u1' })

    await store.logout()

    expect(store.token).toBe('')
    expect(store.user).toBeNull()
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/auth/logout',
      expect.objectContaining({ method: 'POST', credentials: 'include' })
    )
  })
})
