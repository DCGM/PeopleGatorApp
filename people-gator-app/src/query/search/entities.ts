import {
  useInfiniteQuery,
  useQueryClient,
  type InfiniteData,
  type QueryKey,
} from '@tanstack/vue-query'
import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'

import {
  searchEntitiesGetApiV1SearchEntitiesGet,
  type EntityResponse,
  type EntitySortField,
  type FoundEntity,
  type SearchEntitiesGetApiV1SearchEntitiesGetData,
} from '@/client'
import type { SharedQuery } from '@/viewmodels/shared-filters'
import { responseData } from '@/query/api'
import { fetchEntities } from '@/query/entities'
import { queryKeys } from '@/query/keys'
import { listSortParams, sortParams, type SortState } from '@/lib/sorting'
import {
  cursorResultPage,
  SEARCH_CACHE_TIME,
  SEARCH_GC_TIME,
  searchPageSize,
  useRestartSearchPages,
  type InfiniteResultPage,
} from '@/query/search/shared'

export type EntitySearchParams = NonNullable<SearchEntitiesGetApiV1SearchEntitiesGetData['query']>
export type EntitySearchRecord = EntityResponse | FoundEntity

export type EntityResultsParams = {
  query: string
  cursor?: string | null
  hasDetections?: boolean
  hasMentions?: boolean
  processingFilters?: SharedQuery
  limit?: number
  sort?: SortState<EntitySortField>
}

type EntitySearchPage = InfiniteResultPage<FoundEntity, string | null>
type EntityResultsPage = InfiniteResultPage<EntitySearchRecord, string | null>

export function fetchEntitySearch(params: EntitySearchParams, signal?: AbortSignal) {
  return responseData(
    searchEntitiesGetApiV1SearchEntitiesGet({ query: params, signal, throwOnError: true }),
  )
}

async function fetchEntitySearchPage(
  params: EntitySearchParams,
  cursor: string | null,
  pageSize: number,
  signal: AbortSignal,
) {
  const response = await fetchEntitySearch({ ...params, limit: pageSize, cursor }, signal)
  return cursorResultPage(response)
}

export function useEntitySearchQuery(
  params: MaybeRefOrGetter<EntitySearchParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const queryKey = computed(() => queryKeys.search.infiniteEntities(toValue(params)))
  useRestartSearchPages(queryKey)
  return useInfiniteQuery<
    EntitySearchPage,
    Error,
    InfiniteData<EntitySearchPage, string | null>,
    QueryKey,
    string | null
  >({
    queryKey,
    queryFn: ({ pageParam, signal }) => {
      const resolvedParams = toValue(params)
      return fetchEntitySearchPage(
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
 * Infinite people results for the search screen. A blank query browses the
 * entity collection, while a text query uses the ranked search endpoint.
 */
export function useEntityResultsQuery(
  params: MaybeRefOrGetter<EntityResultsParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const queryClient = useQueryClient()
  const queryKey = computed(() => {
    const resolvedParams = toValue(params)
    const query = resolvedParams.query.trim()
    const keyParams = {
      ...resolvedParams.processingFilters,
      'filter.has_detections': resolvedParams.hasDetections,
      'filter.has_mentions': resolvedParams.hasMentions,
      limit: searchPageSize(resolvedParams.limit),
      return_total_count: true,
      cursor: resolvedParams.cursor,
      ...(resolvedParams.sort && sortParams(resolvedParams.sort)),
    }
    return query
      ? queryKeys.search.infiniteEntities({ ...keyParams, 'query.text': [query] })
      : queryKeys.entities.infinite(keyParams)
  })
  watch(
    () => JSON.stringify(queryKey.value),
    () => {
      // Returning to a previously used filter must start at its first page too.
      // Retain that page's cache while dropping cursors/pages loaded for the old visit.
      queryClient.setQueryData<InfiniteData<EntityResultsPage, string | null>>(
        queryKey.value,
        (cached) =>
          cached && {
            ...cached,
            pages: cached.pages.slice(0, 1),
            pageParams: cached.pageParams.slice(0, 1),
          },
        { updatedAt: queryClient.getQueryState(queryKey.value)?.dataUpdatedAt },
      )
    },
    { flush: 'sync' },
  )
  return useInfiniteQuery<
    EntityResultsPage,
    Error,
    InfiniteData<EntityResultsPage, string | null>,
    QueryKey,
    string | null
  >({
    queryKey,
    queryFn: async ({ pageParam, signal }) => {
      const resolvedParams = toValue(params)
      const query = resolvedParams.query.trim()
      const pageSize = searchPageSize(resolvedParams.limit)

      if (query) {
        return fetchEntitySearchPage(
          {
            'query.text': [query],
            ...resolvedParams.processingFilters,
            'filter.has_detections': resolvedParams.hasDetections,
            'filter.has_mentions': resolvedParams.hasMentions,
            limit: pageSize,
            return_total_count: true,
            ...(resolvedParams.sort && sortParams(resolvedParams.sort)),
          },
          pageParam,
          pageSize,
          signal,
        )
      }

      const response = await fetchEntities(
        {
          ...resolvedParams.processingFilters,
          'filter.has_detections': resolvedParams.hasDetections,
          'filter.has_mentions': resolvedParams.hasMentions,
          limit: pageSize,
          return_total_count: true,
          cursor: pageParam,
          ...(resolvedParams.sort && listSortParams(resolvedParams.sort)),
        },
        signal,
      )
      return cursorResultPage(response)
    },
    initialPageParam: computed(() => toValue(params).cursor ?? null),
    getNextPageParam: (lastPage, _pages, lastPageParam) =>
      lastPage.nextPage === lastPageParam ? null : lastPage.nextPage,
    enabled: computed(() => toValue(enabled)),
    staleTime: SEARCH_CACHE_TIME,
    gcTime: SEARCH_GC_TIME,
    refetchOnWindowFocus: false,
  })
}
