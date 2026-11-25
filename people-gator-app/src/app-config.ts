import { reactive } from 'vue'
import { apiBaseUrl } from '@/telemetry'

export interface AppConfig {
  /** Account the app signs in with by itself, so the public can browse without a login page. */
  publicLogin: { username: string; password: string } | null
}

export const appConfig = reactive<AppConfig>({ publicLogin: null })

/** Read the deployment's browser configuration; without it the app asks for a login. */
export async function loadAppConfig(): Promise<void> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/app-config`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(3000),
    })
    if (!response.ok) return
    const config = (await response.json()) as Partial<AppConfig>
    const login = config.publicLogin
    appConfig.publicLogin = login?.username && login.password ? login : null
  } catch {
    console.warn('Application configuration is unavailable')
  }
}
