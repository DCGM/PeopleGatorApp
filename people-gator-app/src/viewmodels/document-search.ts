import type { SharedQuery } from './shared-filters'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import type { PageResponse, PageSortField } from '@/client'
import type { SortState } from '@/lib/sorting'

import { pageContentFilter, type PageContentFilter } from '@/viewmodels/assignment'
import { usePageResultsQuery } from '@/query/search'
import { usePageCards } from '@/viewmodels/page-cards'
export { sourceEntityNames } from '@/viewmodels/page-cards'
export type { DocumentSearchCard } from '@/viewmodels/page-cards'

export function useDocumentSearch(
  searchTerm: MaybeRefOrGetter<string>,
  filter: MaybeRefOrGetter<PageContentFilter>,
  pageSize = 12,
  shared: MaybeRefOrGetter<SharedQuery & { 'filter.document_id'?: string[] }> = {},
  enabled: MaybeRefOrGetter<boolean> = true,
  sort?: MaybeRefOrGetter<SortState<PageSortField>>,
) {
  const normalizedSearch = computed(() => toValue(searchTerm).trim())
  const contentFilter = computed(() => pageContentFilter(toValue(filter)))
  const pageResultsQuery = usePageResultsQuery(
    computed(() => ({
      query: normalizedSearch.value,
      ...toValue(shared),
      ...contentFilter.value,
      limit: pageSize,
      sort: sort && toValue(sort),
    })),
    enabled,
  )

  const pages = computed(() => {
    const unique = new Map<string, PageResponse>()
    for (const batch of pageResultsQuery.data.value?.pages ?? []) {
      for (const page of batch.items) unique.set(page.source_id, page)
    }
    return [...unique.values()]
  })
  const cards = usePageCards(pages)

  return {
    cards,
    error: pageResultsQuery.error,
    hasNextPage: pageResultsQuery.hasNextPage,
    isFetching: pageResultsQuery.isFetching,
    isFetchingNextPage: pageResultsQuery.isFetchingNextPage,
    isLoading: pageResultsQuery.isPending,
    loadMore: () => {
      if (
        !toValue(enabled) ||
        pageResultsQuery.isFetching.value ||
        !pageResultsQuery.hasNextPage.value
      )
        return Promise.resolve()
      return pageResultsQuery.fetchNextPage({ cancelRefetch: false })
    },
    resultCount: computed(() => {
      return pageResultsQuery.data.value?.pages[0]?.totalCount ?? 0
    }),
  }
}
