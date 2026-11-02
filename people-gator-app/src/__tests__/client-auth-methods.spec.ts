import axios, { AxiosHeaders } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { listEntitiesRouteApiV1EntitiesGet } from '@/client'
import { createClient } from '@/client/client'
import { apiClient } from '@/query/client'
import { getAccessToken, recordAuthenticatedResponse } from '@/query/auth'
vi.mock('@/query/auth', () => ({
  getAccessToken: vi.fn(),
  requireLogin: vi.fn(),
  recordAuthenticatedResponse: vi.fn(),
}))

afterEach(() => {
  sessionStorage.clear()
  vi.unstubAllGlobals()
})

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
    vi.mocked(getAccessToken).mockResolvedValue(token)
    const auth = apiClient.getConfig().auth
    if (typeof auth !== 'function') throw new Error('Expected scheme-aware authentication')
    expect(await auth({ type: 'http', scheme: 'bearer' })).toBe(token)
    expect(await auth({ type: 'apiKey', name: 'X-API-Key' })).toBeUndefined()
  })

  it('delegates bearer renewal to the configured authentication provider', async () => {
    vi.mocked(getAccessToken).mockResolvedValue('provider-renewed-token')
    const auth = apiClient.getConfig().auth
    if (typeof auth !== 'function') throw new Error('Expected scheme-aware authentication')
    expect(await auth({ type: 'http', scheme: 'bearer' })).toBe('provider-renewed-token')
    expect(getAccessToken).toHaveBeenCalled()
  })
  it('only resets reauthentication recovery after a successful bearer request', async () => {
    vi.mocked(recordAuthenticatedResponse).mockClear()
    const adapter = async (config: import('axios').InternalAxiosRequestConfig) => ({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    })
    await apiClient.instance.get('/api/v1/health', { adapter })
    expect(recordAuthenticatedResponse).not.toHaveBeenCalled()
    await apiClient.instance.get('/api/v1/me', {
      adapter,
      headers: { Authorization: 'Bearer valid' },
    })
    expect(recordAuthenticatedResponse).toHaveBeenCalledOnce()
  })
})
