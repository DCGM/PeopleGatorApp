import { isAxiosError } from 'axios'
import { computed, ref } from 'vue'
import { appConfig } from '@/app-config'
import { apiBaseUrl } from '@/telemetry'
import { getTokenTokenLoginPost, refreshTokenTokenRefreshPost, type TokenResponse } from '@/client'
import { client } from '@/client/client.gen'

const accessTokenKey = 'people-gator.access-token'
const refreshTokenKey = 'people-gator.refresh-token'
const signedOutKey = 'people-gator.signed-out'

let pendingToken: Promise<string> | undefined

export class SignInRequiredError extends Error {
  override name = 'SignInRequiredError'
  constructor() {
    super('Sign in required')
  }
}

function storage() {
  return typeof window === 'undefined' ? undefined : window.sessionStorage
}

function tokenClaims(token: string | null | undefined): {
  exp?: number
  uid?: unknown
  sub?: unknown
} {
  try {
    const payload = token?.split('.')[1]
    if (!payload) return {}
    const unpadded = payload.replace(/-/g, '+').replace(/_/g, '/')
    const normalized = unpadded.padEnd(Math.ceil(unpadded.length / 4) * 4, '=')
    return JSON.parse(atob(normalized))
  } catch {
    return {}
  }
}

function tokenExpiry(token: string): number {
  const claims = tokenClaims(token)
  // Tokens issued before the user UUID claim are rejected by the API; refresh them.
  if (typeof claims.uid !== 'string') return 0
  return (claims.exp ?? 0) * 1000
}

function storedUser() {
  const subject = tokenClaims(storage()?.getItem(accessTokenKey)).sub
  return typeof subject === 'string' ? subject : undefined
}

/** Username of this tab's session, including the public account. */
export const currentUser = ref(storedUser())
/** The session belongs to the deployment's public account, not to a person. */
export const isPublicSession = computed(
  () => !!currentUser.value && currentUser.value === appConfig.publicLogin?.username,
)
/** No session can be obtained without the login page. */
export const signInRequired = ref(false)

function persistTokens(tokens: TokenResponse) {
  storage()?.setItem(accessTokenKey, tokens.access_token)
  storage()?.setItem(refreshTokenKey, tokens.refresh_token)
  storage()?.removeItem(signedOutKey)
  currentUser.value = storedUser()
  signInRequired.value = false
  return tokens.access_token
}

function clearTokens() {
  storage()?.removeItem(accessTokenKey)
  storage()?.removeItem(refreshTokenKey)
  currentUser.value = undefined
}

function isRejected(error: unknown) {
  const status = isAxiosError(error) ? error.response?.status : undefined
  return status === 401 || status === 403
}

/** Sign in with a username and password; the token carries every scope the account holds. */
export async function login(username: string, password: string) {
  const response = await getTokenTokenLoginPost({
    body: { username, password },
    throwOnError: true,
  })
  return persistTokens(response.data)
}

/** Sign in as the deployment's public account. */
export async function loginAsPublic() {
  const account = appConfig.publicLogin
  if (!account) throw new SignInRequiredError()
  return login(account.username, account.password)
}

/** End this tab's session and show the login page instead of the public account. */
export function signOut() {
  clearTokens()
  storage()?.setItem(signedOutKey, '1')
  signInRequired.value = true
}

async function requestTokens(): Promise<string> {
  const savedRefreshToken = storage()?.getItem(refreshTokenKey)
  const previousUser = currentUser.value

  if (savedRefreshToken) {
    try {
      const response = await refreshTokenTokenRefreshPost({
        body: { refresh_token: savedRefreshToken },
        throwOnError: true,
      })
      return persistTokens(response.data)
    } catch (error) {
      if (!isRejected(error)) throw error
      clearTokens()
    }
  }

  // A person whose session ended signs in again; they are not turned into the public account.
  const account = appConfig.publicLogin
  const endedPersonalSession = previousUser !== undefined && previousUser !== account?.username
  if (account && !endedPersonalSession && !storage()?.getItem(signedOutKey)) {
    try {
      return await loginAsPublic()
    } catch (error) {
      if (!isRejected(error)) throw error
    }
  }

  signInRequired.value = true
  throw new SignInRequiredError()
}

export async function getAccessToken() {
  const savedToken = storage()?.getItem(accessTokenKey)
  if (savedToken && tokenExpiry(savedToken) > Date.now() + 30_000) return savedToken
  // Wait for the login page instead of retrying on every request.
  if (signInRequired.value) throw new SignInRequiredError()

  pendingToken ??= requestTokens().finally(() => {
    pendingToken = undefined
  })
  return pendingToken
}

client.setConfig({
  // SDK endpoint paths start with '/'; a root base must be empty to avoid '//host' URLs.
  baseURL: apiBaseUrl.replace(/\/+$/, ''),
  auth: (scheme) => (scheme.scheme === 'bearer' ? getAccessToken() : undefined),
  throwOnError: true,
})

export { client as apiClient }
