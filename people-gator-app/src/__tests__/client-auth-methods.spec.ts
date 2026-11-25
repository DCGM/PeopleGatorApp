import axios, { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { listEntitiesRouteApiV1EntitiesGet } from '@/client'
import { createClient } from '@/client/client'
import { retryUnlessClientError } from '@/query/api'
import { appConfig } from '@/app-config'
import {
  apiClient,
  currentUser,
  getAccessToken,
  isPublicSession,
  login,
  loginAsPublic,
  signInRequired,
  signOut,
} from '@/query/client'

afterEach(() => {
  signOut()
  sessionStorage.clear()
  signInRequired.value = false
  appConfig.publicLogin = null
})

const freshToken = (sub = 'alice') =>
  `header.${btoa(JSON.stringify({ exp: 4102444800, uid: 'u', sub }))}.signature`
const tokens = (sub?: string) => ({
  status: 200,
  data: { access_token: freshToken(sub), refresh_token: 'r', token_type: 'bearer' },
})
const guest = { username: 'guest', password: 'open' }

type Reply = { status: number; data?: unknown }

/** Route API calls through a fake adapter that answers with the given replies in order. */
async function withReplies<T>(
  replies: Reply[],
  run: (calls: InternalAxiosRequestConfig[]) => Promise<T>,
): Promise<T> {
  const calls: InternalAxiosRequestConfig[] = []
  const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
    calls.push(config)
    const reply = replies.shift() ?? { status: 500 }
    const response = { data: reply.data, status: reply.status, statusText: '', headers: {}, config }
    if (reply.status >= 400) {
      throw new AxiosError('failed', String(reply.status), config, undefined, response)
    }
    return response
  })
  const previous = apiClient.getConfig().axios
  apiClient.setConfig({ axios: axios.create({ adapter }) })
  try {
    return await run(calls)
  } finally {
    apiClient.setConfig({ axios: previous })
  }
}

describe('generated client authentication alternatives', () => {
  it.each(['bearer', 'api-key'] as const)(
    'sends only the selected %s credential',
    async (method) => {
      const adapter = vi.fn(async (config) => ({
        data: { items: [], limit: 1 },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }))
      const client = createClient({
        baseURL: 'https://example.test',
        axios: axios.create({ adapter }),
        auth: (scheme) =>
          method === 'bearer' && scheme.scheme === 'bearer'
            ? 'jwt-token'
            : method === 'api-key' && scheme.name === 'X-API-Key'
              ? 'integration-key'
              : undefined,
      })
      await listEntitiesRouteApiV1EntitiesGet({ client, query: { limit: 1 }, throwOnError: true })
      const headers = AxiosHeaders.from(adapter.mock.calls[0]![0].headers)
      expect(headers.get('Authorization')).toBe(
        method === 'bearer' ? 'Bearer jwt-token' : undefined,
      )
      expect(headers.get('X-API-Key')).toBe(method === 'api-key' ? 'integration-key' : undefined)
    },
  )

  it('the browser auth callback returns a token only for the bearer scheme', async () => {
    const token = `header.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 3600, uid: 'u' }))}.signature`
    sessionStorage.setItem('people-gator.access-token', token)
    const auth = apiClient.getConfig().auth
    if (typeof auth !== 'function') throw new Error('Expected scheme-aware authentication')
    expect(await auth({ type: 'http', scheme: 'bearer' })).toBe(token)
    expect(await auth({ type: 'apiKey', name: 'X-API-Key' })).toBeUndefined()
  })

  it('refreshes a stored token issued before the user UUID claim', async () => {
    const legacy = `header.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 3600 }))}.signature`
    const fresh = `header.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 3600, uid: 'u' }))}.signature`
    sessionStorage.setItem('people-gator.access-token', legacy)
    sessionStorage.setItem('people-gator.refresh-token', 'refresh')
    const adapter = vi.fn(async (config) => ({
      data: { access_token: fresh, refresh_token: 'rotated', token_type: 'bearer' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }))
    const previous = apiClient.getConfig().axios
    apiClient.setConfig({ axios: axios.create({ adapter }) })
    try {
      const auth = apiClient.getConfig().auth
      if (typeof auth !== 'function') throw new Error('Expected scheme-aware authentication')
      expect(await auth({ type: 'http', scheme: 'bearer' })).toBe(fresh)
      expect(adapter.mock.calls[0]![0].url).toContain('/token/refresh')
      expect(sessionStorage.getItem('people-gator.refresh-token')).toBe('rotated')
    } finally {
      apiClient.setConfig({ axios: previous })
    }
  })

  it('opens as the configured public account without a login page', async () => {
    appConfig.publicLogin = guest
    await withReplies([tokens('guest')], async (calls) => {
      expect(await getAccessToken()).toBe(freshToken('guest'))
      expect(calls).toHaveLength(1)
      expect(calls[0]!.url).toMatch(/\/token\/login$/)
      // No scope: the API grants what the account holds, so a browse-only guest is not refused.
      expect(String(calls[0]!.data)).toBe('username=guest&password=open')
      expect(currentUser.value).toBe('guest')
      expect(isPublicSession.value).toBe(true)
      expect(signInRequired.value).toBe(false)
    })
  })

  it('requires the login page without a public account, asking the API only once', async () => {
    await withReplies([], async (calls) => {
      const error = await getAccessToken().catch((cause: unknown) => cause)
      expect(retryUnlessClientError(0, error)).toBe(false)
      expect(signInRequired.value).toBe(true)
      await expect(getAccessToken()).rejects.toThrow('Sign in required')
      expect(calls).toHaveLength(0)
    })
  })

  it('requires the login page when the public account is refused', async () => {
    appConfig.publicLogin = guest
    await withReplies([{ status: 401 }], async () => {
      await expect(getAccessToken()).rejects.toThrow('Sign in required')
      expect(signInRequired.value).toBe(true)
    })
  })

  it('does not treat an unreachable API as signed out', async () => {
    appConfig.publicLogin = guest
    await withReplies([{ status: 503 }], async () => {
      await expect(getAccessToken()).rejects.toThrow('failed')
      expect(signInRequired.value).toBe(false)
    })
  })

  it('signs a person in from the login page and out again', async () => {
    appConfig.publicLogin = guest
    await withReplies([tokens('alice'), tokens('guest')], async (calls) => {
      await login('alice', 'secret')
      expect(String(calls[0]!.data)).toBe('username=alice&password=secret')
      expect(currentUser.value).toBe('alice')
      expect(isPublicSession.value).toBe(false)
      expect(await getAccessToken()).toBe(freshToken('alice'))

      signOut()
      expect(currentUser.value).toBeUndefined()
      expect(sessionStorage.getItem('people-gator.access-token')).toBeNull()
      expect(sessionStorage.getItem('people-gator.refresh-token')).toBeNull()
      // Signing out does not fall back to the public account by itself.
      signInRequired.value = false
      await expect(getAccessToken()).rejects.toThrow('Sign in required')
      expect(calls).toHaveLength(1)

      await loginAsPublic()
      expect(isPublicSession.value).toBe(true)
      expect(await getAccessToken()).toBe(freshToken('guest'))
    })
  })

  it('asks a person to sign in again when their session ends, not the public account', async () => {
    appConfig.publicLogin = guest
    await withReplies([tokens('alice'), { status: 401 }], async (calls) => {
      await login('alice', 'secret')
      sessionStorage.setItem('people-gator.access-token', 'expired')
      await expect(getAccessToken()).rejects.toThrow('Sign in required')
      expect(calls).toHaveLength(2)
      expect(calls[1]!.url).toMatch(/\/token\/refresh$/)
      expect(currentUser.value).toBeUndefined()
    })
  })

  it('renews an ended public session by itself', async () => {
    appConfig.publicLogin = guest
    await withReplies([tokens('guest'), { status: 401 }, tokens('guest')], async (calls) => {
      await getAccessToken()
      sessionStorage.setItem('people-gator.access-token', 'expired')
      expect(await getAccessToken()).toBe(freshToken('guest'))
      expect(calls[2]!.url).toMatch(/\/token\/login$/)
    })
  })
})
