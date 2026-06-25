import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore } from '../../stores/user.js'
import { apiFetch } from '../client.js'

describe('api client', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  function mockFetch(implementation) {
    global.fetch = vi.fn().mockImplementation(implementation)
  }

  it('returns parsed JSON on success', async () => {
    mockFetch(() => Promise.resolve({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      text: async () => JSON.stringify({ id: 1 }),
    }))

    const data = await apiFetch('/api/courses/1')
    expect(data).toEqual({ id: 1 })
  })

  it('deduplicates concurrent GET requests', async () => {
    mockFetch(() =>
      new Promise((resolve) =>
        setTimeout(
          () =>
            resolve({
              ok: true,
              status: 200,
              headers: new Headers({ 'content-type': 'application/json' }),
              text: async () => JSON.stringify({ ok: true }),
            }),
          10
        )
      )
    )

    const [a, b] = await Promise.all([apiFetch('/api/x'), apiFetch('/api/x')])
    expect(a).toEqual({ ok: true })
    expect(b).toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('retries on 5xx and then succeeds', async () => {
    let calls = 0
    mockFetch(() => {
      calls += 1
      if (calls === 1) {
        return Promise.resolve({
          ok: false,
          status: 503,
          headers: new Headers(),
          text: async () => 'busy',
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ recovered: true }),
      })
    })

    const data = await apiFetch('/api/x')
    expect(data).toEqual({ recovered: true })
    expect(calls).toBe(2)
  })

  it('refreshes token on 401 and retries once', async () => {
    const user = useUserStore()
    user.setAuth('old-token', null, { id: 'u1' })

    let calls = 0
    mockFetch(() => {
      calls += 1
      if (calls === 1) {
        return Promise.resolve({
          ok: false,
          status: 401,
          headers: new Headers(),
          text: async () => 'unauthorized',
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ ok: true }),
      })
    })

    user.refreshAccessToken = vi.fn().mockResolvedValue('new-token')

    const data = await apiFetch('/api/x')
    expect(data).toEqual({ ok: true })
    expect(user.refreshAccessToken).toHaveBeenCalledTimes(1)
    expect(calls).toBe(2)
  })

  it('surfaces backend detail message on HTTP error', async () => {
    mockFetch(() =>
      Promise.resolve({
        ok: false,
        status: 400,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ detail: '标题不能为空' }),
      })
    )

    await expect(apiFetch('/api/x', { method: 'POST' })).rejects.toThrow('标题不能为空')
  })
})
