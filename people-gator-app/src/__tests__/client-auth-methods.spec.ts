import axios, { AxiosHeaders } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { listEntitiesRouteApiV1EntitiesGet } from '@/client'
import { createClient } from '@/client/client'
import { apiClient } from '@/query/client'

afterEach(() => sessionStorage.clear())

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
})
