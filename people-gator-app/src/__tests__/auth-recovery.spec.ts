import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const assign = vi.fn()
beforeEach(() => {
  sessionStorage.clear()
  vi.clearAllMocks()
  vi.stubGlobal('location', {
    origin: 'http://localhost:3000',
    pathname: '/people',
    search: '?q=Ada',
    hash: '#details',
    assign,
  })
})
afterEach(() => vi.unstubAllGlobals())
async function page() {
  vi.resetModules()
  return import('@/query/auth')
}

it('stops repeated API rejection after one reauthentication round trip', async () => {
  let auth = await page()
  expect(() => auth.requireLogin(true)).toThrow('Sign in required')
  let target = new URL(assign.mock.calls[assign.mock.calls.length - 1]![0], location.origin)
  expect(target.searchParams.get('expired')).toBe('1')
  expect(target.searchParams.get('return')).toBe('/people?q=Ada#details')
  auth = await page()
  expect(() => auth.requireLogin(true)).toThrow('Sign in required')
  target = new URL(assign.mock.calls[assign.mock.calls.length - 1]![0], location.origin)
  expect(target.searchParams.get('error')).toBe('api-rejected')
})

it('permits future recovery after an authenticated resource request succeeds', async () => {
  let auth = await page()
  expect(() => auth.requireLogin(true)).toThrow()
  auth.recordAuthenticatedResponse()
  auth = await page()
  expect(() => auth.requireLogin(true)).toThrow()
  expect(new URL(assign.mock.calls[assign.mock.calls.length - 1]![0], location.origin).searchParams.has('error')).toBe(
    false,
  )
})
