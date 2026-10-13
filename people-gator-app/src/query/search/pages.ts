import { useInfiniteQuery, type InfiniteData, type QueryKey } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  searchPagesGetApiV1SearchPagesGet,
  type FoundPage,
  type PageResponse,
  type SearchPagesGetApiV1SearchPagesGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'
import { fetchPages } from '@/query/media'
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
  'filter.library'?: string[]
  'filter.document_id'?: string[]
  'filter.has_entities'?: boolean
  'filter.has_faces'?: boolean
  'filter.has_mentions'?: boolean
  cursor?: string | null
  limit?: number
}

type PageResultsPage = InfiniteResultPage<PageSearchRecord, string | null>

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
        ...(resolvedParams['filter.library'] && {
          'filter.library': resolvedParams['filter.library'],
        }),
        ...(resolvedParams['filter.document_id'] && {
          'filter.document_id': resolvedParams['filter.document_id'],
        }),
        'filter.has_entities': resolvedParams['filter.has_entities'],
        'filter.has_faces': resolvedParams['filter.has_faces'],
        'filter.has_mentions': resolvedParams['filter.has_mentions'],
        cursor: resolvedParams.cursor,
        limit: searchPageSize(resolvedParams.limit),
        return_total_count: true,
      }
      return query
        ? queryKeys.search.infinitePages({ ...keyParams, 'query.text': [query] })
        : queryKeys.pages.results(keyParams)
    }),
    queryFn: async ({ pageParam, signal }) => {
      const resolvedParams = toValue(params)
      const query = resolvedParams.query.trim()
      const pageSize = searchPageSize(resolvedParams.limit)
      const filters = {
        ...(resolvedParams['filter.library'] && {
          'filter.library': resolvedParams['filter.library'],
        }),
        ...(resolvedParams['filter.document_id'] && {
          'filter.document_id': resolvedParams['filter.document_id'],
        }),
        'filter.has_entities': resolvedParams['filter.has_entities'],
        'filter.has_faces': resolvedParams['filter.has_faces'],
        'filter.has_mentions': resolvedParams['filter.has_mentions'],
      }

      if (query) {
        return fetchPageSearchPage(
          { 'query.text': [query], ...filters, limit: pageSize, return_total_count: true },
          pageParam,
          pageSize,
          signal,
        )
      }

      const response = await fetchPages(
        { ...filters, limit: pageSize, return_total_count: true, cursor: pageParam },
        signal,
      )
      return cursorResultPage(response)
    },
    initialPageParam: computed(() => toValue(params).cursor ?? null),
    getNextPageParam: (lastPage, _pages, lastPageParam) =>
      lastPage.nextPage === lastPageParam ? null : lastPage.nextPage,
    staleTime: SEARCH_CACHE_TIME,
    gcTime: SEARCH_GC_TIME,
    refetchOnWindowFocus: false,
  })
}
