import { onMounted, ref } from 'vue'
import { getAccessToken } from '@/query/client'

export function useCanAnnotate() {
  const allowed = ref(false)
  onMounted(async () => {
    try {
      const token = await getAccessToken()
      const encoded = token.split('.')[1]!.replace(/-/g, '+').replace(/_/g, '/')
      const claims = JSON.parse(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=')))
      const granted = claims.scopes ?? claims.scope
      const scopes = Array.isArray(granted) ? granted : String(granted ?? '').split(' ')
      allowed.value = scopes.includes('people-gator:annotate')
    } catch {
      allowed.value = false
    }
  })
  return allowed
}
