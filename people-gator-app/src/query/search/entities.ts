import { useInfiniteQuery, type InfiniteData, type QueryKey } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  searchEntitiesGetApiV1SearchEntitiesGet,
  type FoundEntity,
  type SearchEntitiesGetApiV1SearchEntitiesGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'
import {
  cursorResultPage,
  SEARCH_CACHE_TIME,
  SEARCH_GC_TIME,
  searchPageSize,
  useRestartSearchPages,
  type InfiniteResultPage,
} from '@/query/search/shared'

export type EntitySearchParams = NonNullable<SearchEntitiesGetApiV1SearchEntitiesGetData['query']>

type EntitySearchPage = InfiniteResultPage<FoundEntity, string | null>

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
