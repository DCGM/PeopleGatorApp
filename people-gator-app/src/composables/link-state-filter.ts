import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { parseLinkStates } from '@/lib/entity-links'
export function useLinkStateFilter<
  State extends string = ReturnType<typeof parseLinkStates>[number],
>(
  key = 'link_state',
  parse: (value: unknown) => State[] = parseLinkStates as (value: unknown) => State[],
) {
  const route = useRoute()
  const router = useRouter()
  return computed({
    get: () => parse(route.query[key]),
    set: (value: State[]) => {
      void router.push({ query: { ...route.query, [key]: value.length ? value : undefined } })
    },
  })
}
