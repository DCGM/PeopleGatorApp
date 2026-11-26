import {
  useInfiniteQuery,
  useQueryClient,
  type InfiniteData,
  type QueryKey,
} from '@tanstack/vue-query'
import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'

import type { FoundPerson, PersonResponse, PersonSortField } from '@/client'
import type { PeopleCountQuery } from '@/viewmodels/people-counts'
import type { LifeDateQuery } from '@/viewmodels/people-life-dates'
import type { SharedQuery } from '@/viewmodels/shared-filters'
import { fetchPeople, searchPeople, type PeopleSearchParams } from '@/query/people'
import { queryKeys } from '@/query/keys'
import { listSortParams, sortParams, type SortState } from '@/lib/sorting'
import {
  cursorResultPage,
  SEARCH_CACHE_TIME,
  SEARCH_GC_TIME,
  searchPageSize,
  type InfiniteResultPage,
} from '@/query/search/shared'

/** A People search card record from the typed person API (#123). */
export type PersonSearchRecord = PersonResponse | FoundPerson

export type PeopleResultsParams = {
  query: string
  cursor?: string | null
  hasDetections?: boolean
  hasMentions?: boolean
  processingFilters?: SharedQuery & PeopleCountQuery & LifeDateQuery
  limit?: number
  sort?: SortState<PersonSortField>
}

type PeopleResultsPage = InfiniteResultPage<PersonSearchRecord, string | null>

async function fetchPeopleSearchPage(
  params: PeopleSearchParams,
  cursor: string | null,
  pageSize: number,
  signal: AbortSignal,
) {
  return cursorResultPage(await searchPeople({ ...params, limit: pageSize, cursor }, signal))
}

/**
 * Infinite people results for the search screen. A blank query browses
 * `/people`, while a text query uses the ranked `/search-people` endpoint.
 */
export function usePeopleResultsQuery(
  params: MaybeRefOrGetter<PeopleResultsParams>,
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
      ? queryKeys.search.infinitePeople({ ...keyParams, 'query.text': [query] })
      : queryKeys.entities.people(keyParams)
  })
  watch(
    () => JSON.stringify(queryKey.value),
    () => {
      // Returning to a previously used filter must start at its first page too.
      // Retain that page's cache while dropping cursors/pages loaded for the old visit.
      queryClient.setQueryData<InfiniteData<PeopleResultsPage, string | null>>(
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
    PeopleResultsPage,
    Error,
    InfiniteData<PeopleResultsPage, string | null>,
    QueryKey,
    string | null
  >({
    queryKey,
    queryFn: async ({ pageParam, signal }) => {
      const resolvedParams = toValue(params)
      const query = resolvedParams.query.trim()
      const pageSize = searchPageSize(resolvedParams.limit)

      if (query) {
        return fetchPeopleSearchPage(
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

      const response = await fetchPeople(
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
