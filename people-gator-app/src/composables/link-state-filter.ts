import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { parseLinkStates } from '@/lib/entity-links'
export function useLinkStateFilter() {
  const route = useRoute()
  const router = useRouter()
  return computed({
    get: () => parseLinkStates(route.query.link_state),
    set: (value) => {
      void router.push({ query: { ...route.query, link_state: value.length ? value : undefined } })
    },
  })
}
