import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { DocumentResponse, DocumentSortField, PageResponse } from '@/client'
import type { SortState } from '@/lib/sorting'
import { usePageListQuery } from '@/query/media'
import { useDocumentResultsQuery } from '@/query/search/documents'
import { unassignedQuery, type UnassignedFilter } from './document-filters'
import type { SharedQuery } from './shared-filters'
import { usePageCards } from '@/viewmodels/page-cards'

function uniqueSources<T extends { source_id: string }>(pages: Array<{ items: T[] }> = []) {
  return [
    ...new Map(pages.flatMap((page) => page.items).map((item) => [item.source_id, item])).values(),
  ]
}

export function documentTitle(document: Pick<DocumentResponse, 'name' | 'document_id'>) {
  return document.name?.trim() || `Document ${document.document_id}`
}

export function useDocumentList(
  search: MaybeRefOrGetter<string>,
  shared: MaybeRefOrGetter<SharedQuery>,
  unassigned: MaybeRefOrGetter<UnassignedFilter> = 'all',
  pageSize = 12,
  enabled: MaybeRefOrGetter<boolean> = true,
  sort?: MaybeRefOrGetter<SortState<DocumentSortField>>,
) {
  const query = useDocumentResultsQuery(
    computed(() => ({
      query: toValue(search),
      filters: { ...toValue(shared), ...unassignedQuery(toValue(unassigned)) },
      limit: pageSize,
      sort: sort && toValue(sort),
    })),
    enabled,
  )
  return {
    documents: computed(() => uniqueSources<DocumentResponse>(query.data.value?.pages)),
    resultCount: computed(() => query.data.value?.pages[0]?.totalCount ?? 0),
    error: query.error,
    isLoading: computed(() => query.isPending.value && toValue(enabled)),
    hasNextPage: query.hasNextPage,
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    loadMore: () => {
      if (!toValue(enabled) || query.isFetching.value || !query.hasNextPage.value)
        return Promise.resolve()
      return query.fetchNextPage({ cancelRefetch: false })
    },
    retry: () => (query.isFetchNextPageError.value ? query.fetchNextPage() : query.refetch()),
  }
}

// Previews show this document's pages under the shared configuration. The document
// matched it, so its own scope replaces the shared document selection.
export function useDocumentGroup(
  document: MaybeRefOrGetter<DocumentResponse>,
  pageSize = 4,
  shared: MaybeRefOrGetter<SharedQuery> = {},
) {
  const narrowed = computed(() => {
    const rest = { ...toValue(shared) }
    delete rest['filter.library']
    delete rest['filter.document_source_id']
    return Object.keys(rest).length > 0 ? rest : undefined
  })
  const query = usePageListQuery(
    computed(() => ({
      ...narrowed.value,
      'filter.document_source_id': [toValue(document).source_id],
      // The same archive page-ID order as the scan list and gallery for this document.
      sort: 'page_id' as const,
      limit: Math.min(pageSize, 4),
      return_total_count: true,
    })),
  )
  const registeredCount = usePageListQuery(
    computed(() => ({
      'filter.document_source_id': [toValue(document).source_id],
      limit: 0,
      return_total_count: true,
    })),
    computed(() => !!narrowed.value),
  )
  const pages = computed(() =>
    uniqueSources<PageResponse>(query.data.value?.pages.slice(0, 1)).slice(0, 4),
  )
  return {
    cards: usePageCards(pages),
    narrowed: computed(() => !!narrowed.value),
    totalCount: computed(
      () =>
        (narrowed.value
          ? registeredCount.data.value?.pages[0]?.total_count
          : query.data.value?.pages[0]?.total_count) ?? null,
    ),
    filteredCount: computed(() => query.data.value?.pages[0]?.total_count ?? null),
    error: query.error,
    isLoading: query.isPending,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    loadMore: query.fetchNextPage,
    retry: () => (query.isFetchNextPageError.value ? query.fetchNextPage() : query.refetch()),
  }
}
