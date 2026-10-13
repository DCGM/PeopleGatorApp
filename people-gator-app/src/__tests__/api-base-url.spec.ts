import { afterEach, describe, expect, it, vi } from 'vitest'

describe('API base URL', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it.each([
    ['/', 'https://pr-123.preview.peoplegator.dev'],
    ['/gateway/', 'https://pr-123.preview.peoplegator.dev/gateway'],
    ['https://backend.example.test/', 'https://backend.example.test'],
    [undefined, 'https://dev.people-gator.capturemyhand.com'],
  ])('resolves login and API paths with base %s', async (baseUrl, expectedBase) => {
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', baseUrl)
    const { apiClient } = await import('@/query/client')

    for (const path of ['/token/login', '/api/v1/health']) {
      const url = apiClient.buildUrl({ url: path })
      const resolved = new URL(url, 'https://pr-123.preview.peoplegator.dev/people/example')

      expect(url).not.toMatch(/^\/\//)
      expect(resolved.href).toBe(`${expectedBase}${path}`)
    }
  })
})
