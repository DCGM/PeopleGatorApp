import { useInfiniteQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  searchFacesGetApiV1SearchFacesGet,
  type SearchFacesGetApiV1SearchFacesGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'
import { cursorResultPage, searchPageSize } from '@/query/search/shared'

export type FaceSearchParams = NonNullable<SearchFacesGetApiV1SearchFacesGetData['query']>

export function fetchFaceSearch(params: FaceSearchParams, signal?: AbortSignal) {
  return responseData(
    searchFacesGetApiV1SearchFacesGet({ query: params, signal, throwOnError: true }),
  )
}

export function useFaceSearchQuery(
  params: MaybeRefOrGetter<FaceSearchParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.search.infiniteFaces(toValue(params))),
    queryFn: async ({ pageParam, signal }) => {
      const resolvedParams = toValue(params)
      const pageSize = searchPageSize(resolvedParams.limit)
      const response = await fetchFaceSearch(
        { ...resolvedParams, limit: pageSize, cursor: pageParam },
        signal,
      )
      return cursorResultPage(response)
    },
    initialPageParam: computed(() => toValue(params).cursor ?? null),
    getNextPageParam: (lastPage, _pages, lastPageParam) =>
      lastPage.nextPage === lastPageParam ? null : lastPage.nextPage,
    enabled: computed(() => toValue(enabled)),
  })
}
