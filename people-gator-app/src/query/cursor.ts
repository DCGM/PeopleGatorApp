import { useQueryClient, type QueryKey } from '@tanstack/vue-query'
import { watch, toValue, type MaybeRefOrGetter } from 'vue'

export type CursorParams = {
  cursor?: string | null
}

export type CursorResponse = {
  cursor?: string | null
}

export function initialCursor<Params extends CursorParams>(
  params?: MaybeRefOrGetter<Params | undefined>,
) {
  return toValue(params)?.cursor ?? null
}

export function withCursor<Params extends object>(
  params: Params | undefined,
  cursor: string | null,
): Params & CursorParams {
  return { ...params, cursor } as Params & CursorParams
}

export function nextCursor(page: CursorResponse, previousCursor: string | null) {
  const cursor = page.cursor ?? null
  return cursor === previousCursor ? null : cursor
}

/** Re-entering an effective filter starts at its first page, retaining that page's data. */
export function useFirstPageOnFilterChange(key: MaybeRefOrGetter<QueryKey>) {
  const client = useQueryClient()
  watch(
    () => JSON.stringify(toValue(key)),
    () => {
      const queryKey = toValue(key)
      client.setQueryData<{ pages: unknown[]; pageParams: unknown[] }>(
        queryKey,
        (cached) =>
          cached && {
            ...cached,
            pages: cached.pages.slice(0, 1),
            pageParams: cached.pageParams.slice(0, 1),
          },
        { updatedAt: client.getQueryState(queryKey)?.dataUpdatedAt },
      )
    },
    { flush: 'sync' },
  )
}
