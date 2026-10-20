import type { EvidenceQuery } from './evidence-filters'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntityLinkState, DocumentResponse, PageResponse } from '@/client'
import { usePageListQuery } from '@/query/media'
import { useDocumentResultsQuery } from '@/query/search/documents'
import { documentFiltersQuery, documentFilterError, type DocumentFilters } from './document-filters'
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
  filters: MaybeRefOrGetter<DocumentFilters>,
  pageSize = 12,
  evidence: MaybeRefOrGetter<EvidenceQuery> = {},
  evidenceValid: MaybeRefOrGetter<boolean> = true,
) {
  const filterError = computed(() => documentFilterError(toValue(filters)))
  const query = useDocumentResultsQuery(
    computed(() => ({
      query: toValue(search),
      filters: { ...documentFiltersQuery(toValue(filters)), ...toValue(evidence) },
      limit: pageSize,
    })),
    computed(() => !filterError.value && toValue(evidenceValid)),
  )
  return {
    documents: computed(() => uniqueSources<DocumentResponse>(query.data.value?.pages)),
    resultCount: computed(() => query.data.value?.pages[0]?.totalCount ?? 0),
    filterError,
    error: query.error,
    isLoading: computed(() => query.isPending.value && !filterError.value),
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    loadMore: query.fetchNextPage,
    retry: () => (query.isFetchNextPageError.value ? query.fetchNextPage() : query.refetch()),
  }
}

export function useDocumentGroup(
  document: MaybeRefOrGetter<DocumentResponse>,
  pageSize = 4,
  linkStates: MaybeRefOrGetter<EntityLinkState[]> = [],
  evidence: MaybeRefOrGetter<EvidenceQuery> = {},
) {
  const query = usePageListQuery(
    computed(() => ({
      'filter.library': [toValue(document).library],
      'filter.document_id': [toValue(document).document_id],
      ...(toValue(linkStates).length && { 'filter.entity_link_state': toValue(linkStates) }),
      ...toValue(evidence),
      limit: Math.min(pageSize, 4),
      return_total_count: true,
    })),
  )
  const registeredCount = usePageListQuery(
    computed(() => ({
      'filter.library': [toValue(document).library],
      'filter.document_id': [toValue(document).document_id],
      limit: 0,
      return_total_count: true,
    })),
    computed(() => Object.keys(toValue(evidence)).length > 0 || toValue(linkStates).length > 0),
  )
  const pages = computed(() =>
    uniqueSources<PageResponse>(query.data.value?.pages.slice(0, 1)).slice(0, 4),
  )
  return {
    cards: usePageCards(pages),
    totalCount: computed(
      () =>
        (Object.keys(toValue(evidence)).length || toValue(linkStates).length
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
