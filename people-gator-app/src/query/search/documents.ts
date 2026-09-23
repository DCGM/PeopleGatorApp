import { useInfiniteQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  searchDocumentsGetApiV1SearchDocumentsGet,
  type SearchDocumentsGetApiV1SearchDocumentsGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'
import { cursorResultPage, searchPageSize } from '@/query/search/shared'

export type DocumentSearchParams = NonNullable<
  SearchDocumentsGetApiV1SearchDocumentsGetData['query']
>

export function fetchDocumentSearch(params: DocumentSearchParams, signal?: AbortSignal) {
  return responseData(
    searchDocumentsGetApiV1SearchDocumentsGet({ query: params, signal, throwOnError: true }),
  )
}

export function useDocumentSearchQuery(
  params: MaybeRefOrGetter<DocumentSearchParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.search.infiniteDocuments(toValue(params))),
    queryFn: async ({ pageParam, signal }) => {
      const resolvedParams = toValue(params)
      const pageSize = searchPageSize(resolvedParams.limit)
      const response = await fetchDocumentSearch(
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
