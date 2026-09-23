import { useInfiniteQuery, type InfiniteData, type QueryKey } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  searchPagesGetApiV1SearchPagesGet,
  type FoundPage,
  type PageResponse,
  type SearchPagesGetApiV1SearchPagesGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { fetchFaces } from '@/query/faces'
import { queryKeys } from '@/query/keys'
import { fetchPages } from '@/query/media'
import { fetchTextMentions } from '@/query/text-mentions'
import {
  cursorResultPage,
  SEARCH_CACHE_TIME,
  SEARCH_GC_TIME,
  searchPageSize,
  type InfiniteResultPage,
} from '@/query/search/shared'

export type PageSearchParams = NonNullable<SearchPagesGetApiV1SearchPagesGetData['query']>
export type PageSearchRecord = PageResponse | FoundPage

export type PageResultsParams = {
  query: string
  assignment?: 'face' | 'text_mention'
  cursor?: string | null
  limit?: number
}

type PageResultsPage = InfiniteResultPage<PageSearchRecord, string | null>

async function pageHasAssignment(
  sourceId: string,
  assignment: NonNullable<PageResultsParams['assignment']>,
  signal: AbortSignal,
) {
  let cursor: string | null = null

  do {
    const previousCursor: string | null = cursor
    const response: {
      items: Array<{ entity_id?: string | null }>
      cursor?: string | null
    } =
      assignment === 'face'
        ? await fetchFaces({ 'filter.source_id': [sourceId], limit: 100, cursor }, signal)
        : await fetchTextMentions({ 'filter.source_id': [sourceId], limit: 100, cursor }, signal)

    if (response.items.some((item) => item.entity_id)) return true
    cursor = response.cursor ?? null
    if (cursor === previousCursor) break
  } while (cursor)

  return false
}

async function filterPageAssignments(
  page: PageResultsPage,
  assignment: PageResultsParams['assignment'],
  signal: AbortSignal,
): Promise<PageResultsPage> {
  if (!assignment) return page

  const matches = await Promise.all(
    page.items.map((item) => pageHasAssignment(item.source_id, assignment, signal)),
  )
  return {
    ...page,
    items: page.items.filter((_item, index) => matches[index]),
  }
}

export function fetchPageSearch(params: PageSearchParams, signal?: AbortSignal) {
  return responseData(
    searchPagesGetApiV1SearchPagesGet({ query: params, signal, throwOnError: true }),
  )
}

async function fetchPageSearchPage(
  params: PageSearchParams,
  cursor: string | null,
  pageSize: number,
  signal: AbortSignal,
) {
  const response = await fetchPageSearch({ ...params, limit: pageSize, cursor }, signal)
  return cursorResultPage(response)
}

export function usePageSearchQuery(
  params: MaybeRefOrGetter<PageSearchParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.search.infinitePages(toValue(params))),
    queryFn: ({ pageParam, signal }) => {
      const resolvedParams = toValue(params)
      return fetchPageSearchPage(
        resolvedParams,
        pageParam,
        searchPageSize(resolvedParams.limit),
        signal,
      )
    },
    initialPageParam: computed(() => toValue(params).cursor ?? null),
    getNextPageParam: (lastPage, _pages, lastPageParam) =>
      lastPage.nextPage === lastPageParam ? null : lastPage.nextPage,
    enabled: computed(() => toValue(enabled)),
  })
}

/**
 * Infinite page results for the document search screen. A blank query browses
 * pages; a text query uses ranked page search.
 */
export function usePageResultsQuery(params: MaybeRefOrGetter<PageResultsParams>) {
  return useInfiniteQuery<
    PageResultsPage,
    Error,
    InfiniteData<PageResultsPage, string | null>,
    QueryKey,
    string | null
  >({
    queryKey: computed(() => {
      const resolvedParams = toValue(params)
      const query = resolvedParams.query.trim()
      const keyParams = {
        assignment: resolvedParams.assignment,
        cursor: resolvedParams.cursor,
        limit: searchPageSize(resolvedParams.limit),
        return_total_count: true,
      }
      return query
        ? queryKeys.search.infinitePages({ ...keyParams, 'query.text': [query] })
        : queryKeys.pages.infinite(keyParams)
    }),
    queryFn: async ({ pageParam, signal }) => {
      const resolvedParams = toValue(params)
      const query = resolvedParams.query.trim()
      const pageSize = searchPageSize(resolvedParams.limit)

      if (query) {
        return filterPageAssignments(
          await fetchPageSearchPage(
            { 'query.text': [query], limit: pageSize, return_total_count: true },
            pageParam,
            pageSize,
            signal,
          ),
          resolvedParams.assignment,
          signal,
        )
      }

      const response = await fetchPages(
        { limit: pageSize, return_total_count: true, cursor: pageParam },
        signal,
      )
      return filterPageAssignments(cursorResultPage(response), resolvedParams.assignment, signal)
    },
    initialPageParam: computed(() => toValue(params).cursor ?? null),
    getNextPageParam: (lastPage, _pages, lastPageParam) =>
      lastPage.nextPage === lastPageParam ? null : lastPage.nextPage,
    staleTime: SEARCH_CACHE_TIME,
    gcTime: SEARCH_GC_TIME,
    refetchOnWindowFocus: false,
  })
}
