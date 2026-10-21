import { useQueryClient, type InfiniteData, type QueryKey } from '@tanstack/vue-query'
import { toValue, watch, type MaybeRefOrGetter } from 'vue'

/** Returning to a previous search selection starts with its first cached page. */
export function useRestartSearchPages(key: MaybeRefOrGetter<QueryKey>) {
  const client = useQueryClient()
  watch(
    () => JSON.stringify(toValue(key)),
    () => {
      const queryKey = toValue(key)
      client.setQueryData<InfiniteData<unknown>>(
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

export type InfiniteResultPage<Item, PageParam = number> = {
  items: Item[]
  totalCount: number
  nextPage: PageParam | undefined
}

type SearchResponse<Item> = {
  items: Item[]
  total_count?: number | null
}

type CursorResponse<Item> = SearchResponse<Item> & {
  cursor?: string | null
}

export const DEFAULT_SEARCH_PAGE_SIZE = 20
export const SEARCH_CACHE_TIME = 10 * 60_000
export const SEARCH_GC_TIME = 60 * 60_000

export function searchPageSize(limit: number | undefined) {
  return limit ?? DEFAULT_SEARCH_PAGE_SIZE
}

export function cursorResultPage<Item>(
  response: CursorResponse<Item>,
): InfiniteResultPage<Item, string | null> {
  return {
    items: response.items,
    totalCount: response.total_count ?? response.items.length,
    nextPage: response.cursor ?? null,
  }
}
