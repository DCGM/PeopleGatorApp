import { apiBaseUrl } from '@/telemetry'
import { client } from '@/client/client.gen'
import { getAccessToken, requireLogin, recordAuthenticatedResponse } from './auth'
import { AxiosHeaders } from 'axios'
export { getAccessToken } from './auth'

client.setConfig({
  baseURL: apiBaseUrl.replace(/\/+$/, ''),
  auth: (scheme) => (scheme.scheme === 'bearer' ? getAccessToken() : undefined),
  throwOnError: true,
})
client.instance.interceptors.response.use(
  (response) => {
    const authorization = AxiosHeaders.from(response.config.headers).get('Authorization')
    if (typeof authorization === 'string' && authorization.toLowerCase().startsWith('bearer '))
      recordAuthenticatedResponse()
    return response
  },
  (error) => {
    if (error.response?.status === 401) requireLogin(true)
    return Promise.reject(error)
  },
)
export { client as apiClient }
