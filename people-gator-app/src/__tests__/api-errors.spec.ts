import { AxiosError, type AxiosResponse } from 'axios'
import { describe, expect, it } from 'vitest'
import { apiErrorCode, retryUnlessClientError } from '@/query/api'

const failure = (status: number, data: unknown = {}) =>
  new AxiosError('failed', 'ERR_BAD_RESPONSE', undefined, undefined, {
    status,
    data,
  } as AxiosResponse)

describe('API errors (#134)', () => {
  it('reads the code of an API error body', () => {
    expect(apiErrorCode(failure(422, { detail: { code: 'invalid_search', message: 'x' } }))).toBe(
      'invalid_search',
    )
    // Request validation errors carry a list, not a code.
    expect(apiErrorCode(failure(422, { detail: [{ msg: 'x' }] }))).toBeUndefined()
    expect(apiErrorCode(new Error('offline'))).toBeUndefined()
  })

  it('does not retry a request the API rejected, but retries transient failures', () => {
    for (const status of [400, 401, 403, 404, 422])
      expect(retryUnlessClientError(0, failure(status))).toBe(false)
    for (const error of [failure(408), failure(429), failure(500), failure(503), new Error('x')]) {
      expect(retryUnlessClientError(0, error)).toBe(true)
      expect(retryUnlessClientError(2, error)).toBe(true)
      expect(retryUnlessClientError(3, error)).toBe(false)
    }
  })
})
