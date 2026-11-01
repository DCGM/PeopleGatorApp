import { afterEach, describe, expect, it, vi } from 'vitest'
import { login, logout, getAccessToken, safeReturnPath } from '@/query/auth'

afterEach(() => {
  sessionStorage.clear()
  vi.unstubAllGlobals()
})

describe('issuer session transport', () => {
  it.each([
    'https://evil.test',
    '//evil.test',
    '/\\evil.test',
    '/login.html',
    '/staging-login.html',
  ])('rejects unsafe return %s', (path) => {
    expect(safeReturnPath(path)).toBe('/')
  })
  it('retains application query and fragment', () => {
    expect(safeReturnPath('/people?name=Ada#faces')).toBe('/people?name=Ada#faces')
  })
  it('logs in directly without bundled credentials and coalesces refresh', async () => {
    const token = `h.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 3600, uid: 'actor' }))}.s`
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: token, refresh_token: 'refresh' }),
    })
    vi.stubGlobal('fetch', fetch)
    await login('alice', 'entered-password')
    expect(fetch.mock.calls[0]![0]).toContain('/token/login')
    expect(String(fetch.mock.calls[0]![1].body)).toBe('username=alice&password=entered-password')
    sessionStorage.removeItem('people-gator.access-token')
    await Promise.all([getAccessToken(), getAccessToken(), getAccessToken()])
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[1]![0]).toContain('/token/refresh')
  })
  it('reports failed login without storing a session', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
    await expect(login('alice', 'wrong')).rejects.toThrow('Check your username and password.')
    expect(sessionStorage.length).toBe(0)
  })
  it('allows docs to check an expired session without navigation', async () => {
    sessionStorage.setItem('people-gator.refresh-token', 'expired')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
    await expect(getAccessToken({ redirect: false })).rejects.toThrow('Session expired')
    expect(sessionStorage.getItem('people-gator.refresh-token')).toBeNull()
    expect(sessionStorage.getItem('people-gator.access-token')).toBeNull()
  })

  it('revokes and clears the refresh session on logout', async () => {
    sessionStorage.setItem('people-gator.refresh-token', 'refresh')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
    // jsdom records unsupported navigation; session revocation still completes.
    await logout()
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/token/logout'),
      expect.objectContaining({ body: '{"refresh_token":"refresh"}' }),
    )
    expect(sessionStorage.length).toBe(0)
  })
})
