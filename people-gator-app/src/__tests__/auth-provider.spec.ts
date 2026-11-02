import { beforeEach, describe, expect, it, vi } from 'vitest'
import { UserManager } from 'oidc-client-ts'
import { jwtVerify } from 'jose'
import { OidcAuthenticationProvider } from '@/query/auth-provider'

vi.mock('oidc-client-ts', async (original) => {
  const source = await original<typeof import('oidc-client-ts')>()
  return { ...source, UserManager: vi.fn() }
})
vi.mock('jose', () => ({ createRemoteJWKSet: vi.fn(() => 'public-keys'), jwtVerify: vi.fn() }))

const authority = 'https://provider.test/realm'
function fakeManager() {
  return {
    getUser: vi.fn().mockResolvedValue(null),
    signinRedirect: vi.fn(),
    signinSilent: vi.fn(),
    signinRedirectCallback: vi.fn(),
    signoutRedirect: vi.fn(),
    signoutRedirectCallback: vi.fn(),
    removeUser: vi.fn(),
    metadataService: {
      getMetadata: vi.fn().mockResolvedValue({ issuer: authority, jwks_uri: authority + '/certs' }),
    },
  }
}
let manager: ReturnType<typeof fakeManager>
beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  history.replaceState(null, '', '/')
  manager = fakeManager()
  vi.mocked(UserManager).mockImplementation(function () {
    return manager as unknown as UserManager
  })
  vi.mocked(jwtVerify).mockResolvedValue({ payload: { sub: 'alice', aud: 'browser' } } as never)
})

describe('standard OIDC authentication adapter', () => {
  it('uses in-memory tokens and transient PKCE transaction storage', async () => {
    const provider = new OidcAuthenticationProvider(authority, 'browser', 'openid profile')
    sessionStorage.setItem('people-gator.access-token', 'legacy')
    sessionStorage.setItem('people-gator.refresh-token', 'legacy-refresh')
    expect(await provider.accessToken()).toBeUndefined()
    const settings = vi.mocked(UserManager).mock.calls[0]![0]
    expect(settings.disablePKCE).toBe(false)
    expect(settings.response_type).toBe('code')
    expect(settings.client_secret).toBeUndefined()
    expect(sessionStorage.length).toBe(0)
    await settings.userStore!.set('user', 'token-test')
    expect(sessionStorage.length).toBe(0)
  })
  it('requests a docs callback and nonce while retaining operation state', async () => {
    const provider = new OidcAuthenticationProvider(authority, 'browser', 'openid')
    await provider.signIn('/docs?view=example#/users/me')
    expect(manager.signinRedirect).toHaveBeenCalledWith(
      expect.objectContaining({
        redirect_uri: location.origin + '/docs',
        state: { returnTo: '/docs?view=example#/users/me' },
        nonce: expect.any(String),
      }),
    )
  })
  it('coalesces concurrent refresh and does not inspect access-token claims', async () => {
    const provider = new OidcAuthenticationProvider(authority, 'browser', 'openid')
    manager.getUser.mockResolvedValue({
      access_token: 'old',
      refresh_token: 'refresh',
      expires_in: 1,
      id_token: 'validated-id',
    })
    manager.signinSilent.mockResolvedValue({
      access_token: 'opaque-fresh',
      expires_in: 300,
      id_token: 'validated-id',
    })
    expect(await Promise.all([provider.accessToken(), provider.accessToken()])).toEqual([
      'opaque-fresh',
      'opaque-fresh',
    ])
    expect(manager.signinSilent).toHaveBeenCalledOnce()
  })
  it('validates returned identity signature, issuer and client audience before restoring navigation', async () => {
    const provider = new OidcAuthenticationProvider(authority, 'browser', 'openid')
    history.replaceState(null, '', '/auth-callback.html?code=temporary&state=matching')
    manager.signinRedirectCallback.mockResolvedValue({
      id_token: 'signed-id',
      state: { returnTo: '/people?q=Ada#details' },
    })
    await provider.initialize()
    expect(jwtVerify).toHaveBeenCalledWith(
      'signed-id',
      'public-keys',
      expect.objectContaining({
        issuer: authority,
        audience: 'browser',
        algorithms: ['ES256', 'RS256'],
      }),
    )
    expect(location.pathname + location.search + location.hash).toBe('/people?q=Ada#details')
    expect(Object.values(sessionStorage)).not.toContain('signed-id')
  })
  it('clears a rejected identity token without preserving tokens', async () => {
    const provider = new OidcAuthenticationProvider(authority, 'browser', 'openid')
    history.replaceState(null, '', '/auth-callback.html?code=temporary&state=matching')
    manager.signinRedirectCallback.mockResolvedValue({
      id_token: 'bad-id',
      state: { returnTo: '/people' },
    })
    vi.mocked(jwtVerify).mockRejectedValue(new Error('invalid identity'))
    await expect(provider.initialize()).rejects.toThrow('Sign-in could not be completed')
    expect(manager.removeUser).toHaveBeenCalled()
    expect(sessionStorage.length).toBe(0)
  })
  it('does not retry a failed anonymous SSO check indefinitely', async () => {
    const provider = new OidcAuthenticationProvider(authority, 'browser', 'openid')
    const hint = `people-gator.oidc-session:${authority}:browser`
    sessionStorage.setItem(hint, '1')
    sessionStorage.setItem(hint + ':recovering', '1')
    expect(await provider.accessToken()).toBeUndefined()
    expect(manager.signinRedirect).not.toHaveBeenCalled()
  })
})
