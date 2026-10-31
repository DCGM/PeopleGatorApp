import { afterEach, describe, expect, it, vi } from 'vitest'
import { openobserveRum } from '@openobserve/browser-rum'
import { openobserveLogs } from '@openobserve/browser-logs'
import { initializeTelemetry, isApiUrl } from '../telemetry'

vi.mock('@openobserve/browser-rum', () => ({
  openobserveRum: { init: vi.fn(), setGlobalContext: vi.fn() },
}))
vi.mock('@openobserve/browser-logs', () => ({
  openobserveLogs: { init: vi.fn(), setGlobalContext: vi.fn() },
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe('API trace allowlist', () => {
  it.each([
    ['/api/v1/entities', true], ['/token/login', true], ['/assets/image.png', false],
    ['https://other.example/api/v1/entities', false],
    ['https://app.example.evil/api/v1/entities', false],
    ['https://app.example@evil.example/api/v1/entities', false], ['/api-other', false],
  ])('matches only application API requests: %s', (url, allowed) => {
    expect(isApiUrl(url, '/', 'https://app.example')).toBe(allowed)
  })
  it('supports a separate API origin and path prefix', () => {
    const base = 'https://api.example/gator'
    expect(isApiUrl(`${base}/api/v1/entities`, base, 'https://app.example')).toBe(true)
    expect(isApiUrl('https://api.example/api/v1/entities', base, 'https://app.example')).toBe(false)
    expect(isApiUrl('/api/v1/entities', base, 'https://app.example')).toBe(false)
  })
})

it('initializes RUM and error logs with runtime metadata and no replay', async () => {
  const config = {
    enabled: true, clientToken: 'synthetic-rum', site: 'collector.example',
    organizationIdentifier: 'default', applicationId: 'people-gator-app',
    service: 'people-gator-app', env: 'preview', version: 'abc123',
    sessionSampleRate: 100, context: { pr_number: '94', commit: 'abc123' },
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(config)))
  await initializeTelemetry()
  expect(openobserveRum.init).toHaveBeenCalledWith(expect.objectContaining({
    clientToken: 'synthetic-rum', env: 'preview', version: 'abc123',
    defaultPrivacyLevel: 'mask', sessionReplaySampleRate: 0,
    allowedTracingUrls: [{ match: expect.any(Function), propagatorTypes: ['tracecontext'] }],
  }))
  expect(openobserveLogs.init).toHaveBeenCalledWith(expect.objectContaining({
    forwardErrorsToLogs: true, insecureHTTP: false,
  }))
  expect(openobserveRum.setGlobalContext).toHaveBeenCalledWith(config.context)
})

it.each([Response.json({ enabled: false }), new Response('', { status: 404 })])(
  'keeps the app usable when telemetry is disabled or backend is older', async (response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    await initializeTelemetry()
    expect(openobserveRum.init).not.toHaveBeenCalled()
  },
)

it('contains configuration failures without exposing SDK error details', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('synthetic-secret')))
  const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
  await expect(initializeTelemetry()).resolves.toBeUndefined()
  expect(warning).toHaveBeenCalledWith('Browser monitoring is unavailable')
})
