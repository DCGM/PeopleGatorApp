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
