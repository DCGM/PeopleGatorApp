import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  login,
  logout,
  getAccessToken,
  safeReturnPath,
  initializeAuthentication,
} from '@/query/auth'
import { authenticationProvider } from '@/query/auth-provider'

vi.mock('@/query/auth-provider', async (original) => {
  const source = await original<typeof import('@/query/auth-provider')>()
  const provider = {
    initialize: vi.fn(),
    accessToken: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
    finishSignOut: vi.fn(),
  }
  return { ...source, authenticationProvider: () => provider }
})
const provider = authenticationProvider()
beforeEach(() => vi.clearAllMocks())
afterEach(() => sessionStorage.clear())

describe('provider-independent authentication facade', () => {
  it.each([
    'https://evil.test',
    '//evil.test',
    '/\\evil.test',
    '/login.html',
    '/staging-login.html',
    '/auth-callback.html',
  ])('rejects unsafe return %s', (path) => expect(safeReturnPath(path)).toBe('/'))
  it('preserves query and fragment', () =>
    expect(safeReturnPath('/people?q=Ada#faces')).toBe('/people?q=Ada#faces'))
  it('delegates sign-in, initialization and logout without collecting credentials', async () => {
    await initializeAuthentication()
    await login('/docs?view=test#operation')
    await logout()
    expect(provider.initialize).toHaveBeenCalledOnce()
    expect(provider.signIn).toHaveBeenCalledWith('/docs?view=test#operation')
    expect(provider.signOut).toHaveBeenCalledOnce()
    expect(sessionStorage.length).toBe(0)
  })
  it('returns opaque provider tokens without assuming UUID or expiry claims', async () => {
    vi.mocked(provider.accessToken).mockResolvedValue('opaque-provider-token')
    expect(await getAccessToken()).toBe('opaque-provider-token')
  })
  it('allows anonymous docs without redirecting', async () => {
    vi.mocked(provider.accessToken).mockResolvedValue(undefined)
    await expect(getAccessToken({ redirect: false })).rejects.toThrow('Sign in required')
    expect(provider.signIn).not.toHaveBeenCalled()
  })
})
