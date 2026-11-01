/** Browser session transport. Issuer calls are independent of the resource SDK. */
export const accessTokenKey = 'people-gator.access-token'
export const refreshTokenKey = 'people-gator.refresh-token'
const authBaseUrl = (import.meta.env.VITE_AUTH_BASE_URL ?? '').replace(/\/+$/, '')
export type Tokens = { access_token: string; refresh_token: string; token_type: string }
let pendingToken: Promise<string> | undefined
let redirecting = false

export function safeReturnPath(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\r\n]/.test(value))
    return '/'
  const url = new URL(value, window.location.origin)
  return url.origin === window.location.origin &&
    !['/login.html', '/staging-login.html'].includes(url.pathname)
    ? url.pathname + url.search + url.hash
    : '/'
}

export function tokenExpiry(token: string): number {
  try {
    const payload = token.split('.')[1]!
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const claims = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')))
    return typeof claims.uid === 'string' && typeof claims.exp === 'number' ? claims.exp * 1000 : 0
  } catch {
    return 0
  }
}

export function persistTokens(tokens: Tokens): string {
  if (!tokens.access_token || !tokens.refresh_token) throw new Error('Missing session')
  sessionStorage.setItem(accessTokenKey, tokens.access_token)
  sessionStorage.setItem(refreshTokenKey, tokens.refresh_token)
  return tokens.access_token
}

async function exchange(path: string, body: URLSearchParams | string): Promise<Tokens> {
  const response = await fetch(authBaseUrl + path, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'omit',
    signal: AbortSignal.timeout(10000),
    headers: {
      'Content-Type':
        body instanceof URLSearchParams ? 'application/x-www-form-urlencoded' : 'application/json',
    },
    body,
  })
  if (!response.ok)
    throw new Error(
      response.status === 401 || response.status === 403
        ? 'Check your username and password.'
        : 'Sign-in service unavailable. Try again.',
    )
  return response.json()
}

export async function login(username: string, password: string) {
  return persistTokens(await exchange('/token/login', new URLSearchParams({ username, password })))
}

export function redirectToLogin(expired = false): void {
  sessionStorage.removeItem(accessTokenKey)
  sessionStorage.removeItem(refreshTokenKey)
  if (!redirecting) {
    redirecting = true
    const returnTo = safeReturnPath(location.pathname + location.search + location.hash)
    location.assign(
      '/login.html?' +
        new URLSearchParams({ return: returnTo, ...(expired ? { expired: '1' } : {}) }),
    )
  }
}

export function requireLogin(expired = false): never {
  redirectToLogin(expired)
  throw new Error('Sign in required')
}

export async function getAccessToken(options: { redirect?: boolean } = {}): Promise<string> {
  const saved = sessionStorage.getItem(accessTokenKey)
  const hadSession = Boolean(saved || sessionStorage.getItem(refreshTokenKey))
  if (saved && tokenExpiry(saved) > Date.now() + 30_000) return saved
  pendingToken ??= (async () => {
    const refresh = sessionStorage.getItem(refreshTokenKey)
    if (!refresh) throw new Error('Sign in required')
    try {
      return persistTokens(
        await exchange('/token/refresh', JSON.stringify({ refresh_token: refresh })),
      )
    } catch {
      sessionStorage.removeItem(accessTokenKey)
      sessionStorage.removeItem(refreshTokenKey)
      throw new Error('Session expired')
    }
  })().finally(() => {
    pendingToken = undefined
  })
  try {
    return await pendingToken
  } catch (error) {
    if (options.redirect !== false) return requireLogin(hadSession)
    throw error
  }
}

export async function logout() {
  const refresh = sessionStorage.getItem(refreshTokenKey)
  sessionStorage.removeItem(accessTokenKey)
  sessionStorage.removeItem(refreshTokenKey)
  try {
    if (refresh)
      await fetch(authBaseUrl + '/token/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
        credentials: 'omit',
        cache: 'no-store',
        signal: AbortSignal.timeout(5000),
      })
  } finally {
    location.assign('/login.html')
  }
}
