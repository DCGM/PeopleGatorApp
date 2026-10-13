import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import type { EntityLinkState, PageResponse } from '@/client'

import { pageContentFilter, type PageContentFilter } from '@/viewmodels/assignment'
import { usePageResultsQuery } from '@/query/search'
import { usePageCards } from '@/viewmodels/page-cards'
export { sourceEntityNames } from '@/viewmodels/page-cards'
export type { DocumentSearchCard } from '@/viewmodels/page-cards'

export function useDocumentSearch(
  searchTerm: MaybeRefOrGetter<string>,
  filter: MaybeRefOrGetter<PageContentFilter>,
  pageSize = 12,
  scope: MaybeRefOrGetter<{ library?: string; documentId?: string }> = {},
  linkStates: MaybeRefOrGetter<EntityLinkState[]> = [],
) {
  const normalizedSearch = computed(() => toValue(searchTerm).trim())
  const contentFilter = computed(() => pageContentFilter(toValue(filter)))
  const pageResultsQuery = usePageResultsQuery(
    computed(() => {
      const { library, documentId } = toValue(scope)
      return {
        query: normalizedSearch.value,
        ...(toValue(linkStates).length && { 'filter.entity_link_state': toValue(linkStates) }),
        ...(library && { 'filter.library': [library] }),
        ...(documentId && { 'filter.document_id': [documentId] }),
        ...contentFilter.value,
        limit: pageSize,
      }
    }),
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
    isFetchingNextPage: pageResultsQuery.isFetchingNextPage,
    isLoading: pageResultsQuery.isPending,
    loadMore: pageResultsQuery.fetchNextPage,
    resultCount: computed(() => {
      return pageResultsQuery.data.value?.pages[0]?.totalCount ?? 0
    }),
  }
}
