/** Shared application/docs facade. No provider endpoints, token decoding or token storage. */
import { authenticationProvider, safeReturnPath } from './auth-provider'
export { safeReturnPath } from './auth-provider'

let redirecting = false
const apiRetryKey = 'people-gator.api-reauthentication'

export function recordAuthenticatedResponse(): void {
  sessionStorage.removeItem(apiRetryKey)
}
export function initializeAuthentication(): Promise<void> {
  return authenticationProvider().initialize()
}
export function login(returnTo = '/'): Promise<void> {
  return authenticationProvider().signIn(safeReturnPath(returnTo))
}
export function logout(): Promise<void> {
  return authenticationProvider().signOut()
}
export function finishLogout(): Promise<void> {
  return authenticationProvider().finishSignOut()
}

export function redirectToLogin(expired = false): void {
  if (redirecting) return
  redirecting = true
  const returnTo = safeReturnPath(location.pathname + location.search + location.hash)
  const previous = Number(sessionStorage.getItem(apiRetryKey) || 0)
  const repeated = expired && previous > 0 && Date.now() - previous < 60_000
  if (expired) sessionStorage.setItem(apiRetryKey, String(Date.now()))
  location.assign(
    '/login.html?' +
      new URLSearchParams({
        return: returnTo,
        ...(repeated ? { error: 'api-rejected' } : expired ? { expired: '1' } : {}),
      }),
  )
}
export function requireLogin(expired = false): never {
  redirectToLogin(expired)
  throw new Error('Sign in required')
}
export async function getAccessToken(options: { redirect?: boolean } = {}): Promise<string> {
  const token = await authenticationProvider().accessToken()
  if (token) return token
  if (options.redirect !== false) return requireLogin()
  throw new Error('Sign in required')
}
