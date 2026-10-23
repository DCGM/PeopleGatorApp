import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { parseLinkStates } from '@/lib/entity-links'
export function useLinkStateFilter(key = 'link_state') {
  const route = useRoute()
  const router = useRouter()
  return computed({
    get: () => parseLinkStates(route.query[key]),
    set: (value) => {
      void router.push({ query: { ...route.query, [key]: value.length ? value : undefined } })
    },
  })
}
