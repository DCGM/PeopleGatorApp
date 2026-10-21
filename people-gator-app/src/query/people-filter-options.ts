import { useInfiniteQuery, useQueries, useQuery } from '@tanstack/vue-query'
import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import {
  listApiKeysRouteApiV1ApiKeysGet,
  documentLibraryFilterOptionsRouteApiV1DocumentLibraryFilterOptionsGet,
  listUserFilterOptionsRouteApiV1UserFilterOptionsGet,
} from '@/client'
import { responseData } from '@/query/api'
import { fetchDocuments, fetchPages } from '@/query/media'
import { fetchPageSearch } from '@/query/search/pages'
import type { DocumentResponse, PageResponse } from '@/client'
import { fetchDocumentSearch } from '@/query/search/documents'

export type FilterOption = { id: string; label: string }
export type FilterOptionKind = 'document' | 'page' | 'user' | 'api-key' | 'library'

export function documentOptionLabel(
  doc: Pick<DocumentResponse, 'library' | 'name' | 'document_id'>,
) {
  return `${doc.library} / ${doc.name?.trim() || doc.document_id}`
}
export function pageOptionLabel(page: Pick<PageResponse, 'library' | 'page_id'>) {
  return `${page.library} / ${page.page_id}`
}
/** Pages are listed within the selected documents, else libraries, when present. */
export type PageOptionScope = { libraries?: string[]; documentIds?: string[] }

export function usePeopleFilterOptions(
  kind: FilterOptionKind,
  search: MaybeRefOrGetter<string>,
  enabled: MaybeRefOrGetter<boolean> = true,
  pageScope: MaybeRefOrGetter<PageOptionScope> = {},
) {
  const normalizedSearch = computed(() => toValue(search).trim())
  const scope = computed(() => {
    const { libraries = [], documentIds = [] } = toValue(pageScope)
    return kind !== 'page'
      ? {}
      : {
          ...(documentIds.length
            ? { 'filter.document_source_id': [...documentIds].sort() }
            : libraries.length && { 'filter.library': [...libraries].sort() }),
        }
  })
  const query = useInfiniteQuery({
    queryKey: computed(() => [
      'people-filter-options',
      kind,
      normalizedSearch.value,
      ...(kind === 'page' ? [scope.value] : []),
    ]),
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
            label: documentOptionLabel(doc),
          })),
          cursor: response.cursor,
        }
      }
      if (kind === 'page') {
        const term = normalizedSearch.value
        const response = term
          ? await fetchPageSearch({ ...pagination, ...scope.value, 'query.text': [term] }, signal)
          : await fetchPages({ ...pagination, ...scope.value, sort: 'library' }, signal)
        return {
          items: response.items.map((page) => ({
            id: page.source_id,
            label: pageOptionLabel(page),
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

/** Labels for document/page selections that arrived through navigation or a copied link. */
export function useSourceLabels(kind: 'document' | 'page', ids: MaybeRefOrGetter<string[]>) {
  const selected = computed(() => [...new Set(toValue(ids))].sort())
  const query = useQuery({
    queryKey: computed(() => ['filter-source-labels', kind, selected.value]),
    queryFn: async ({ signal }) => {
      const params = { 'filter.source_id': selected.value, limit: selected.value.length }
      const response =
        kind === 'document'
          ? await fetchDocuments(params, signal)
          : await fetchPages(params, signal)
      return Object.fromEntries(
        response.items.map((item) => [
          item.source_id,
          kind === 'document'
            ? documentOptionLabel(item as DocumentResponse)
            : pageOptionLabel(item as PageResponse),
        ]),
      ) as Record<string, string>
    },
    enabled: computed(() => selected.value.length > 0),
    staleTime: 60_000,
  })
  return {
    labels: computed(() => query.data.value ?? {}),
    /** Selections that resolved to no registered source. */
    missing: computed(() =>
      query.data.value ? selected.value.filter((id) => !(id in query.data.value!)) : [],
    ),
  }
}

/** Resolve copied actor selections even when they are outside the first option page. */
export function useActorLabels(kind: 'user' | 'api-key', ids: MaybeRefOrGetter<string[]>) {
  const selected = computed(() => [...new Set(toValue(ids))].sort())
  const queries = useQueries({
    queries: computed(() =>
      selected.value.map((id) => ({
        queryKey: ['filter-actor-labels', kind, id],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const query = { q: id, limit: 1 }
          if (kind === 'user') {
            const result = await responseData(
              listUserFilterOptionsRouteApiV1UserFilterOptionsGet({
                query,
                signal,
                throwOnError: true,
              }),
            )
            const user = result.items.find((item) => item.user_id === id)
            return user?.display_name
          }
          const result = await responseData(
            listApiKeysRouteApiV1ApiKeysGet({ query, signal, throwOnError: true }),
          )
          const key = result.items.find((item) => item.api_key_id === id)
          return key ? `${key.display_name} (${key.identifier})` : undefined
        },
        staleTime: 60_000,
      })),
    ),
  })
  return {
    labels: computed(() =>
      Object.fromEntries(
        selected.value.flatMap((id, index) => {
          const label = queries.value[index]?.data
          return label ? [[id, label]] : []
        }),
      ),
    ),
  }
}
