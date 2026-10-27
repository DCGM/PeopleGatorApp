import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { DocumentResponse, DocumentSortField } from '@/client'
import type { SortState } from '@/lib/sorting'
import { useDocumentResultsQuery } from '@/query/search/documents'
import { unassignedQuery, type UnassignedFilter } from './document-filters'
import type { SharedQuery } from './shared-filters'

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
    retry: () => {
      if (!toValue(enabled) || query.isFetching.value) return Promise.resolve()
      return query.isFetchNextPageError.value
        ? query.fetchNextPage({ cancelRefetch: false })
        : query.refetch({ cancelRefetch: false })
    },
  }
}
