import { useRoute, useRouter, type LocationQueryRaw, type Router } from 'vue-router'

export type QueryPatch = LocationQueryRaw
export type QueryHistory = 'push' | 'replace'

type Batch = { query: QueryPatch; push: boolean; hash?: string }
const pending = new WeakMap<Router, Batch>()
// Changes sent but not yet visible in the route; later batches build on them.
const inFlight = new WeakMap<Router, QueryPatch>()

/**
 * Merge every query change requested in one tick into a single navigation.
 * Navigation commits asynchronously, so a batch is based on the route plus any
 * changes still in flight; otherwise a later navigation would cancel earlier
 * keys. The batch is shared by every caller on the router; one `push` makes it
 * a history entry.
 */
export function useRouteQueryPatch() {
  const route = useRoute()
  const router = useRouter()

  return function patch(changes: QueryPatch, mode: QueryHistory = 'replace', hash?: string) {
    const current = pending.get(router)
    const batch: Batch = current ?? { query: {}, push: false }
    Object.assign(batch.query, changes)
    batch.push ||= mode === 'push'
    if (hash !== undefined) batch.hash = hash
    if (current) return
    pending.set(router, batch)
    queueMicrotask(() => {
      pending.delete(router)
      const sent = { ...inFlight.get(router), ...batch.query }
      inFlight.set(router, sent)
      const target = { query: { ...route.query, ...sent }, hash: batch.hash ?? route.hash }
      const settled = () => {
        if (inFlight.get(router) === sent) inFlight.delete(router)
      }
      void Promise.resolve(batch.push ? router.push(target) : router.replace(target)).finally(
        settled,
      )
    })
  }
}
