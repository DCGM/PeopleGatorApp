import { useInfiniteQuery } from '@tanstack/vue-query'
import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import {
  listApiKeysRouteApiV1ApiKeysGet,
  documentLibraryFilterOptionsRouteApiV1DocumentLibraryFilterOptionsGet,
  listUserFilterOptionsRouteApiV1UserFilterOptionsGet,
} from '@/client'
import { responseData } from '@/query/api'
import { fetchDocuments } from '@/query/media'
import { fetchDocumentSearch } from '@/query/search/documents'

export type FilterOption = { id: string; label: string }
export type FilterOptionKind = 'document' | 'user' | 'api-key' | 'library'

export function usePeopleFilterOptions(
  kind: FilterOptionKind,
  search: MaybeRefOrGetter<string>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const normalizedSearch = computed(() => toValue(search).trim())
  const query = useInfiniteQuery({
    queryKey: computed(() => ['people-filter-options', kind, normalizedSearch.value]),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam, signal }) => {
      const pagination = { limit: 50, cursor: pageParam }
      if (kind === 'library') {
        const response = await responseData(
          documentLibraryFilterOptionsRouteApiV1DocumentLibraryFilterOptionsGet({
            query: { ...pagination, q: normalizedSearch.value || undefined },
            signal,
            throwOnError: true,
          }),
        )
        return {
          items: response.items.map((item) => ({ id: item.library, label: item.library })),
          cursor: response.cursor,
        }
      }
      if (kind === 'document') {
        const term = normalizedSearch.value
        const response = term
          ? await fetchDocumentSearch({ ...pagination, 'query.text': [term] }, signal)
          : await fetchDocuments(pagination, signal)
        return {
          items: response.items.map((doc) => ({
            id: doc.source_id,
            label: `${doc.library} / ${doc.document_id}`,
          })),
          cursor: response.cursor,
        }
      }
      if (kind === 'user') {
        const response = await responseData(
          listUserFilterOptionsRouteApiV1UserFilterOptionsGet({
            query: { ...pagination, q: normalizedSearch.value || undefined },
            signal,
            throwOnError: true,
          }),
        )
        return {
          items: response.items.map((user) => ({ id: user.user_id, label: user.display_name })),
          cursor: response.cursor,
        }
      }
      const response = await responseData(
        listApiKeysRouteApiV1ApiKeysGet({
          query: { ...pagination, q: normalizedSearch.value || undefined },
          signal,
          throwOnError: true,
        }),
      )
      return {
        items: response.items.map((key) => ({
          id: key.api_key_id,
          label: `${key.display_name} (${key.identifier})`,
        })),
        cursor: response.cursor,
      }
    },
    getNextPageParam: (page) => page.cursor ?? undefined,
    staleTime: 60_000,
    enabled: computed(() => toValue(enabled)),
  })
  // Retain labels for selected options after changing a document search.
  const labels = ref<Record<string, string>>({})
  const allOptions = computed(() => query.data.value?.pages.flatMap((page) => page.items) ?? [])
  watch(
    allOptions,
    (options) => {
      for (const option of options) labels.value[option.id] = option.label
    },
    { immediate: true },
  )
  return {
    options: allOptions,
    labels,
    isLoading: query.isPending,
    error: query.error,
    hasMore: query.hasNextPage,
    isLoadingMore: query.isFetchingNextPage,
    loadMore: query.fetchNextPage,
    retry: query.refetch,
  }
}
