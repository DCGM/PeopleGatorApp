import { openobserveRum } from '@openobserve/browser-rum'
import { openobserveLogs } from '@openobserve/browser-logs'

export const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || 'https://dev.people-gator.capturemyhand.com'
).replace(/\/+$/, '')

export function isApiUrl(value: string, base: string, origin: string): boolean {
  const api = new URL(base || '/', origin)
  const url = new URL(value, origin)
  const prefix = api.pathname.replace(/\/+$/, '')
  return url.origin === api.origin && [
    `${prefix}/api/`, `${prefix}/token/`,
  ].some((path) => url.pathname.startsWith(path))
}

export interface RumConfig {
  enabled: boolean
  clientToken: string
  site: string
  organizationIdentifier: string
  applicationId: string
  service: string
  env: string
  version: string
  sessionSampleRate: number
  context: Record<string, string>
}

export async function initializeTelemetry(): Promise<void> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/rum-config`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(3000),
    })
    if (!response.ok) return
    const config = (await response.json()) as RumConfig
    if (!config.enabled) return
    const common = {
      clientToken: config.clientToken,
      site: config.site,
      organizationIdentifier: config.organizationIdentifier,
      service: config.service,
      env: config.env,
      version: config.version,
      insecureHTTP: false,
      apiVersion: 'v1',
    }
    openobserveRum.init({
      ...common,
      applicationId: config.applicationId,
      trackResources: true,
      trackLongTasks: true,
      trackUserInteractions: true,
      defaultPrivacyLevel: 'mask',
      sessionSampleRate: config.sessionSampleRate,
      sessionReplaySampleRate: 0,
      allowedTracingUrls: [{
        match: (url: string) => isApiUrl(url, apiBaseUrl, window.location.origin),
        propagatorTypes: ['tracecontext'],
      }],
    })
    openobserveRum.setGlobalContext(config.context)
    openobserveLogs.init({ ...common, forwardErrorsToLogs: true })
    openobserveLogs.setGlobalContext(config.context)
  } catch {
    // Monitoring availability must not prevent application startup. Do not log
    // the response or SDK error, which could contain the browser client token.
    console.warn('Browser monitoring is unavailable')
  }
}
