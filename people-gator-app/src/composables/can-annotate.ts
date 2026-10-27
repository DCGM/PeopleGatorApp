import { onMounted, ref } from 'vue'
import { getAccessToken } from '@/query/client'

export function useCanAnnotate() {
  return useHasScope('people-gator:annotate')
}

export function useCanDeleteDetection() {
  return useHasScope('people-gator:admin')
}

function useHasScope(scope: string) {
  const allowed = ref(false)
  onMounted(async () => {
    try {
      const token = await getAccessToken()
      const encoded = token.split('.')[1]!.replace(/-/g, '+').replace(/_/g, '/')
      const claims = JSON.parse(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=')))
      const granted = claims.scopes ?? claims.scope
      const scopes = Array.isArray(granted) ? granted : String(granted ?? '').split(' ')
      allowed.value = scopes.includes(scope)
    } catch {
      allowed.value = false
    }
  })
  return allowed
}
