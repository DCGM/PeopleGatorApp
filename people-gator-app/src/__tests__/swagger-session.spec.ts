import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  connectSwaggerSession,
  docsLoginLink,
  type SwaggerSessionUI,
} from '@/query/swagger-session'
import { getAccessToken, redirectToLogin } from '@/query/auth'

vi.mock('@/query/auth', () => ({
  getAccessToken: vi.fn(),
  redirectToLogin: vi.fn(),
}))

function swagger() {
  const entries = new Map<string, Map<string, unknown>>()
  const ui: SwaggerSessionUI = {
    preauthorizeApiKey: vi.fn((name: string, token: string) => {
      entries.set(name, new Map([['value', token]]))
    }),
    authSelectors: { authorized: () => entries },
    authActions: {
      logout: vi.fn((names: string[]) => {
        names.forEach((name) => entries.delete(name))
      }),
    },
  }
  return { ui, entries, bridge: connectSwaggerSession(ui) }
}

beforeEach(() => {
  sessionStorage.clear()
  vi.clearAllMocks()
  vi.mocked(getAccessToken).mockResolvedValue('app-token')
})

describe('Swagger gateway session', () => {
  it('keeps anonymous docs and manual authorization available', async () => {
    vi.mocked(getAccessToken).mockRejectedValue(new Error('Sign in required'))
    const { ui, bridge } = swagger()
    await bridge.ready()
    expect(getAccessToken).toHaveBeenCalledWith({ redirect: false })
    expect(ui.preauthorizeApiKey).not.toHaveBeenCalled()
    expect(redirectToLogin).not.toHaveBeenCalled()
  })

  it('uses an existing app session and refreshes its token before resource requests', async () => {
    const { ui, bridge } = swagger()
    await bridge.ready()
    expect(getAccessToken).toHaveBeenCalledWith({ redirect: false })
    expect(ui.preauthorizeApiKey).toHaveBeenCalledWith('PeopleGatorBearer', 'app-token')
    vi.mocked(getAccessToken).mockResolvedValue('rotated-token')
    const request = await bridge.intercept({
      url: '/api/v1/entities',
      headers: { Authorization: 'Bearer app-token' },
    })
    expect(request.headers?.Authorization).toBe('Bearer rotated-token')
    expect(ui.preauthorizeApiKey).toHaveBeenLastCalledWith('PeopleGatorBearer', 'rotated-token')
  })

  it('does not redirect anonymous docs when a saved session has expired', async () => {
    vi.mocked(getAccessToken).mockRejectedValue(new Error('Session expired'))
    const { ui, bridge } = swagger()
    await bridge.ready()
    expect(ui.preauthorizeApiKey).not.toHaveBeenCalled()
    expect(redirectToLogin).not.toHaveBeenCalled()
  })

  it.each(['PeopleGatorAPIKey', 'PeopleGatorBearer'])(
    'preserves manual %s authorization',
    async (name) => {
      const { ui, entries, bridge } = swagger()
      entries.set(name, new Map([['value', 'manual']]))
      await bridge.ready()
      expect(getAccessToken).not.toHaveBeenCalled()
      expect(ui.preauthorizeApiKey).not.toHaveBeenCalled()
    },
  )

  it('removes only its own bearer when an API key is selected later', async () => {
    const { ui, entries, bridge } = swagger()
    await bridge.ready()
    entries.set('PeopleGatorAPIKey', new Map([['value', 'api-key']]))
    const request = await bridge.intercept({
      url: '/api/v1/entities',
      headers: { Authorization: 'Bearer app-token', 'X-API-Key': 'api-key' },
    })
    expect(request.headers).toEqual({ 'X-API-Key': 'api-key' })
    expect(ui.authActions.logout).toHaveBeenCalledWith(['PeopleGatorBearer'])
  })

  it.each(['https://elsewhere.test/api/v1/entities', '/openapi.json'])(
    'never sends the app bearer outside trusted resource URLs: %s',
    async (url) => {
      const { bridge } = swagger()
      await bridge.ready()
      const request = await bridge.intercept({
        url,
        headers: { authorization: 'Bearer app-token' },
      })
      expect(request.headers).toEqual({})
    },
  )

  it('does not overwrite manual bearer changes or reauthorize after Swagger logout', async () => {
    const { entries, bridge } = swagger()
    await bridge.ready()
    entries.set('PeopleGatorBearer', new Map([['value', 'manual-token']]))
    vi.mocked(getAccessToken).mockClear()
    const request = await bridge.intercept({
      url: '/api/v1/entities',
      headers: { Authorization: 'Bearer manual-token' },
    })
    expect(request.headers?.Authorization).toBe('Bearer manual-token')
    entries.delete('PeopleGatorBearer')
    await bridge.intercept({ url: '/api/v1/entities' })
    expect(getAccessToken).not.toHaveBeenCalled()
  })

  it('does not restore a managed bearer after authorization changes during refresh', async () => {
    const { entries, bridge } = swagger()
    await bridge.ready()
    let resolve: (token: string) => void = () => {}
    vi.mocked(getAccessToken).mockImplementation(
      () =>
        new Promise<string>((done) => {
          resolve = done
        }),
    )
    const pending = bridge.intercept({
      url: '/api/v1/me',
      headers: { Authorization: 'Bearer app-token' },
    })
    entries.delete('PeopleGatorBearer')
    resolve('rotated-token')
    const request = await pending
    expect(request.headers).toEqual({})
    expect(entries.has('PeopleGatorBearer')).toBe(false)
  })

  it('opens the shared login gateway only from its sign-in link', () => {
    const { bridge } = swagger()
    const link = document.createElement('a')
    link.href = docsLoginLink
    document.body.append(link)
    link.addEventListener('click', bridge.signIn)
    const click = new MouseEvent('click', { bubbles: true, cancelable: true })
    link.dispatchEvent(click)
    expect(click.defaultPrevented).toBe(true)
    expect(redirectToLogin).toHaveBeenCalledOnce()
    link.remove()
  })
})
