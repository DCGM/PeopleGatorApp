import {
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

function storage() {
  return typeof window === 'undefined' ? undefined : window.sessionStorage
}

function tokenExpiry(token: string): number {
  try {
    const payload = token.split('.')[1]
    if (!payload) return 0
    const unpadded = payload.replace(/-/g, '+').replace(/_/g, '/')
    const normalized = unpadded.padEnd(Math.ceil(unpadded.length / 4) * 4, '=')
    const decoded = JSON.parse(atob(normalized)) as { exp?: number }
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

  const response = await getTokenTokenLoginPost({
    body: {
      username: import.meta.env.VITE_API_USERNAME || 'test',
      password: import.meta.env.VITE_API_PASSWORD || 'test',
      scope: tokenScopes,
    },
    throwOnError: true,
  })
  return persistTokens(response.data)
}

export async function getAccessToken() {
  const savedToken = storage()?.getItem(accessTokenKey)
  if (savedToken && tokenExpiry(savedToken) > Date.now() + 30_000) return savedToken

  pendingToken ??= requestTokens().finally(() => {
    pendingToken = undefined
  })
  return pendingToken
}

client.setConfig({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'https://dev.people-gator.capturemyhand.com',
  auth: getAccessToken,
  throwOnError: true,
})

export { client as apiClient }
