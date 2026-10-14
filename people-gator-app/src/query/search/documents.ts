import {
  useInfiniteQuery,
  useQueryClient,
  type InfiniteData,
  type QueryKey,
} from '@tanstack/vue-query'
import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'

import {
  searchDocumentsGetApiV1SearchDocumentsGet,
  type SearchDocumentsGetApiV1SearchDocumentsGetData,
} from '@/client'
import type { DocumentResponse } from '@/client'
import { fetchDocuments, type DocumentListParams } from '@/query/media'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'
import { cursorResultPage, searchPageSize, type InfiniteResultPage } from '@/query/search/shared'

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

export function useDocumentResultsQuery(
  params: MaybeRefOrGetter<{ query: string; filters: DocumentListParams; limit?: number }>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const client = useQueryClient()
  type Page = InfiniteResultPage<DocumentResponse, string | null>
  const apiParams = computed(() => ({
    ...toValue(params).filters,
    limit: toValue(params).limit ?? 12,
    return_total_count: true,
  }))
  const key = computed(() =>
    toValue(params).query.trim()
      ? queryKeys.search.infiniteDocuments({
          ...apiParams.value,
          'query.text': [toValue(params).query.trim()],
        })
      : queryKeys.documents.infinite(apiParams.value),
  )
  watch(
    () => JSON.stringify(key.value),
    () => {
      client.setQueryData<InfiniteData<Page, string | null>>(
        key.value,
        (cached) =>
          cached && {
            ...cached,
            pages: cached.pages.slice(0, 1),
            pageParams: cached.pageParams.slice(0, 1),
          },
        { updatedAt: client.getQueryState(key.value)?.dataUpdatedAt },
      )
    },
    { flush: 'sync' },
  )
  return useInfiniteQuery<Page, Error, InfiniteData<Page, string | null>, QueryKey, string | null>({
    queryKey: key,
    queryFn: async ({ pageParam, signal }) => {
      const query = toValue(params).query.trim()
      const pagination = { ...apiParams.value, cursor: pageParam }
      return cursorResultPage(
        query
          ? await fetchDocumentSearch({ ...pagination, 'query.text': [query] }, signal)
          : await fetchDocuments(pagination, signal),
      )
    },
    initialPageParam: null,
    getNextPageParam: (page, _pages, previous) =>
      page.nextPage === previous ? null : page.nextPage,
    enabled: computed(() => toValue(enabled)),
  })
}
