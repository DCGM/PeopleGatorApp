import axios, { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { listEntitiesRouteApiV1EntitiesGet } from '@/client'
import { createClient } from '@/client/client'
import { retryUnlessClientError } from '@/query/api'
import { apiClient, getAccessToken, signIn, signInProblem } from '@/query/client'

afterEach(() => {
  sessionStorage.clear()
  signInProblem.value = undefined
  vi.unstubAllEnvs()
})

const freshToken = () =>
  `header.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 3600, uid: 'u' }))}.signature`

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

  it('signs in through the browser dialog endpoint without sending credentials', async () => {
    const token = freshToken()
    await withReplies(
      [{ status: 200, data: { access_token: token, refresh_token: 'r', token_type: 'bearer' } }],
      async (calls) => {
        expect(await getAccessToken()).toBe(token)
        expect(calls).toHaveLength(1)
        const url = new URL(calls[0]!.url!)
        expect(url.pathname).toBe('/token/basic')
        expect(calls[0]!.method).toBe('post')
        expect(url.searchParams.get('scope')).toContain('people-gator:browse')
        expect(AxiosHeaders.from(calls[0]!.headers).get('Authorization')).toBeUndefined()
        expect(sessionStorage.getItem('people-gator.refresh-token')).toBe('r')
      },
    )
  })

  it('stays signed out after the dialog is dismissed until the user signs in again', async () => {
    const token = freshToken()
    await withReplies(
      [
        { status: 401 },
        { status: 200, data: { access_token: token, refresh_token: 'r', token_type: 'bearer' } },
      ],
      async (calls) => {
        await expect(getAccessToken()).rejects.toThrow()
        expect(signInProblem.value).toBe('signed-out')
        const waiting = await getAccessToken().catch((error: unknown) => error)
        expect(calls).toHaveLength(1)
        expect(retryUnlessClientError(0, waiting)).toBe(false)
        await signIn()
        expect(signInProblem.value).toBeUndefined()
        expect(await getAccessToken()).toBe(token)
        expect(calls).toHaveLength(2)
      },
    )
  })

  it('reports an account without access', async () => {
    await withReplies([{ status: 403 }], async () => {
      await expect(getAccessToken()).rejects.toThrow()
      expect(signInProblem.value).toBe('forbidden')
    })
  })

  it('does not treat an unreachable API as signed out', async () => {
    await withReplies([{ status: 503 }], async () => {
      await expect(getAccessToken()).rejects.toThrow()
      expect(signInProblem.value).toBeUndefined()
    })
  })

  it('signs in automatically with a configured development account', async () => {
    vi.stubEnv('VITE_API_USERNAME', 'test')
    vi.stubEnv('VITE_API_PASSWORD', 'test')
    const token = freshToken()
    await withReplies(
      [{ status: 200, data: { access_token: token, refresh_token: 'r', token_type: 'bearer' } }],
      async (calls) => {
        expect(await getAccessToken()).toBe(token)
        expect(calls[0]!.url).toMatch(/\/token\/login$/)
      },
    )
  })
})
