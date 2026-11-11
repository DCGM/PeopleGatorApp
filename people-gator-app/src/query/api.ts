import { isAxiosError, type AxiosResponse } from 'axios'

export async function responseData<T>(request: Promise<AxiosResponse<T>>): Promise<T> {
  return (await request).data
}

export function compactParams<T extends Record<string, unknown>>(params: T): T {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  ) as T
}

/** The `code` of an API error body (`{ detail: { code, message } }`), if any. */
export function apiErrorCode(error: unknown): string | undefined {
  if (!isAxiosError(error)) return undefined
  const detail = (error.response?.data as { detail?: { code?: unknown } } | undefined)?.detail
  return typeof detail?.code === 'string' ? detail.code : undefined
}

const TRANSIENT_CLIENT_ERRORS = new Set([408, 429])

/** Retry like Vue Query's default, but not a request the API rejected as invalid. */
export function retryUnlessClientError(failureCount: number, error: unknown) {
  const status = isAxiosError(error) ? error.response?.status : undefined
  const rejected =
    status !== undefined && status >= 400 && status < 500 && !TRANSIENT_CLIENT_ERRORS.has(status)
  return !rejected && failureCount < 3
}
