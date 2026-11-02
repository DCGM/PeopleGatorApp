/** Share the gateway's browser session with Swagger without moving issuer code into the API. */
import { getAccessToken, redirectToLogin } from './auth'

const bearerScheme = 'PeopleGatorBearer'
const apiKeyScheme = 'PeopleGatorAPIKey'
export const docsLoginLink = '/login.html?return=%2Fdocs'

type StoredAuthorization = { get(key: string): unknown } | undefined
export interface SwaggerSessionUI {
  preauthorizeApiKey(name: string, token: string): void
  authSelectors: { authorized(): { get(name: string): StoredAuthorization } }
  authActions: { logout(names: string[]): void }
}
export interface SwaggerRequest {
  url: string
  headers?: Record<string, string>
}

export function connectSwaggerSession(ui: SwaggerSessionUI) {
  let managedToken: string | undefined
  const authorization = (name: string) => ui.authSelectors.authorized().get(name)
  const managed = () =>
    managedToken !== undefined && authorization(bearerScheme)?.get('value') === managedToken

  async function ready() {
    if (authorization(bearerScheme) || authorization(apiKeyScheme)) return
    try {
      const token = await getAccessToken({ redirect: false })
      if (authorization(bearerScheme) || authorization(apiKeyScheme)) return
      managedToken = token
      ui.preauthorizeApiKey(bearerScheme, token)
    } catch {
      // Expired app sessions must not prevent anonymous docs or manual API-key use.
    }
  }

  async function intercept(request: SwaggerRequest): Promise<SwaggerRequest> {
    if (!managed()) return request
    const requestToken = managedToken
    const key = Object.keys(request.headers ?? {}).find(
      (name) => name.toLowerCase() === 'authorization',
    )
    const removeManagedHeader = () => {
      if (key && request.headers?.[key] === `Bearer ${requestToken}`) delete request.headers[key]
    }
    const url = new URL(request.url, location.origin)
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) {
      removeManagedHeader()
      return request
    }
    if (authorization(apiKeyScheme)) {
      removeManagedHeader()
      ui.authActions.logout([bearerScheme])
      managedToken = undefined
      return request
    }
    // Respect explicit/manual Authorization headers instead of replacing them.
    if (key && request.headers?.[key] !== `Bearer ${managedToken}`) return request
    const token = await getAccessToken()
    if (!managed() || authorization(apiKeyScheme)) {
      removeManagedHeader()
      return request
    }
    managedToken = token
    ui.preauthorizeApiKey(bearerScheme, token)
    request.headers ??= {}
    request.headers[key ?? 'Authorization'] = `Bearer ${token}`
    return request
  }

  function signIn(event: MouseEvent) {
    const anchor = event.target instanceof Element ? event.target.closest('a') : null
    if (
      anchor?.getAttribute('href') !== docsLoginLink ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return
    event.preventDefault()
    redirectToLogin()
  }

  return { ready, intercept, signIn }
}
