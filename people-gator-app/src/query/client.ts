import { apiBaseUrl } from '@/telemetry'
import { client } from '@/client/client.gen'
import { getAccessToken, requireLogin } from './auth'
export { getAccessToken } from './auth'

client.setConfig({
  baseURL: apiBaseUrl.replace(/\/+$/, ''),
  auth: (scheme) => (scheme.scheme === 'bearer' ? getAccessToken() : undefined),
  throwOnError: true,
})
client.instance.interceptors.response.use(undefined, (error) => {
  if (error.response?.status === 401) requireLogin(true)
  return Promise.reject(error)
})
export { client as apiClient }
