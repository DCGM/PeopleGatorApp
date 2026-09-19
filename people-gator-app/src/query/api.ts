import type { AxiosResponse } from 'axios'

export async function responseData<T>(request: Promise<AxiosResponse<T>>): Promise<T> {
  return (await request).data
}

export function compactParams<T extends Record<string, unknown>>(params: T): T {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  ) as T
}
