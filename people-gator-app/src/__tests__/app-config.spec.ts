import { afterEach, expect, it, vi } from 'vitest'
import { appConfig, loadAppConfig } from '@/app-config'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  appConfig.publicLogin = null
})

const reply = (body: unknown, ok = true) =>
  vi.fn<typeof fetch>(async () => ({ ok, json: async () => body }) as Response)

it('reads the public login from the API', async () => {
  const fetchMock = reply({ publicLogin: { username: 'guest', password: 'open' } })
  vi.stubGlobal('fetch', fetchMock)
  await loadAppConfig()
  expect(String(fetchMock.mock.calls[0]![0])).toMatch(/\/api\/v1\/app-config$/)
  expect(appConfig.publicLogin).toEqual({ username: 'guest', password: 'open' })
})

it.each([
  ['no public login', reply({ publicLogin: null })],
  ['an incomplete public login', reply({ publicLogin: { username: 'guest', password: '' } })],
  ['an older API', reply({ detail: 'Not Found' }, false)],
  [
    'an unreachable API',
    vi.fn<typeof fetch>(async () => {
      throw new Error('offline')
    }),
  ],
])('asks for a login with %s', async (_, fetchMock) => {
  vi.stubGlobal('fetch', fetchMock)
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  await loadAppConfig()
  expect(appConfig.publicLogin).toBeNull()
})
