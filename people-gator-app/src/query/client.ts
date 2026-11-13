import { isAxiosError } from 'axios'
import { ref } from 'vue'
import { apiBaseUrl } from '@/telemetry'
import {
  getBasicTokenTokenBasicPost,
  getTokenTokenLoginPost,
  refreshTokenTokenRefreshPost,
  type TokenResponse,
} from '@/client'
import { client } from '@/client/client.gen'

const accessTokenKey = 'people-gator.access-token'
const refreshTokenKey = 'people-gator.refresh-token'
const tokenScopes = [
  'people-gator:browse',
  'people-gator:annotate',
  'people-gator:ingest',
  'people-gator:admin',
].join(' ')

let pendingToken: Promise<string> | undefined

/** Why the browser has no session: the sign-in dialog was dismissed or the account was refused. */
export const signInProblem = ref<'signed-out' | 'forbidden'>()

export class SignInRequiredError extends Error {
  override name = 'SignInRequiredError'
  constructor() {
    super('Sign in required')
  }
}

function storage() {
  return typeof window === 'undefined' ? undefined : window.sessionStorage
}

function tokenExpiry(token: string): number {
  try {
    const payload = token.split('.')[1]
    if (!payload) return 0
    const unpadded = payload.replace(/-/g, '+').replace(/_/g, '/')
    const normalized = unpadded.padEnd(Math.ceil(unpadded.length / 4) * 4, '=')
    const decoded = JSON.parse(atob(normalized)) as { exp?: number; uid?: unknown }
    // Tokens issued before the user UUID claim are rejected by the API; refresh them.
    if (typeof decoded.uid !== 'string') return 0
    return (decoded.exp ?? 0) * 1000
  } catch {
    return 0
  }
}

function persistTokens(tokens: TokenResponse) {
  storage()?.setItem(accessTokenKey, tokens.access_token)
  storage()?.setItem(refreshTokenKey, tokens.refresh_token)
  return tokens.access_token
}

async function requestTokens(): Promise<string> {
  const savedRefreshToken = storage()?.getItem(refreshTokenKey)

  if (savedRefreshToken) {
    try {
      const response = await refreshTokenTokenRefreshPost({
        body: { refresh_token: savedRefreshToken },
        throwOnError: true,
      })
      return persistTokens(response.data)
    } catch {
      storage()?.removeItem(accessTokenKey)
      storage()?.removeItem(refreshTokenKey)
    }
  }

  // Local development signs in automatically with the configured account.
  const username = import.meta.env.VITE_API_USERNAME
  if (username) {
    const response = await getTokenTokenLoginPost({
      body: { username, password: import.meta.env.VITE_API_PASSWORD ?? '', scope: tokenScopes },
      throwOnError: true,
    })
    return persistTokens(response.data)
  }

  // A Basic challenge makes the browser ask for credentials, or reuse the ones it remembers.
  try {
    const response = await getBasicTokenTokenBasicPost({
      query: { scope: tokenScopes },
      throwOnError: true,
    })
    return persistTokens(response.data)
  } catch (error) {
    const status = isAxiosError(error) ? error.response?.status : undefined
    if (status === 401 || status === 403) {
      signInProblem.value = status === 401 ? 'signed-out' : 'forbidden'
    }
    throw error
  }
}

export async function getAccessToken() {
  const savedToken = storage()?.getItem(accessTokenKey)
  if (savedToken && tokenExpiry(savedToken) > Date.now() + 30_000) return savedToken
  // Without a session, wait for the user to ask instead of reopening the dialog per request.
  if (signInProblem.value) throw new SignInRequiredError()

  pendingToken ??= requestTokens().finally(() => {
    pendingToken = undefined
  })
  return pendingToken
}

/** Show the browser's sign-in dialog again after it was dismissed. */
export async function signIn() {
  signInProblem.value = undefined
  await getAccessToken()
}

client.setConfig({
  // SDK endpoint paths start with '/'; a root base must be empty to avoid '//host' URLs.
  baseURL: apiBaseUrl.replace(/\/+$/, ''),
  auth: (scheme) => (scheme.scheme === 'bearer' ? getAccessToken() : undefined),
  throwOnError: true,
})

export { client as apiClient }
