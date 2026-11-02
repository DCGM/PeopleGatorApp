/** Shared application/docs facade. No provider endpoints, token decoding or token storage. */
import { authenticationProvider, safeReturnPath } from './auth-provider'
export { safeReturnPath } from './auth-provider'

let redirecting = false
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
  location.assign(
    '/login.html?' +
      new URLSearchParams({ return: returnTo, ...(expired ? { expired: '1' } : {}) }),
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
