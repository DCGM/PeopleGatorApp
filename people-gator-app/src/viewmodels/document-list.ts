import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntityLinkState, DocumentResponse, PageResponse } from '@/client'
import { useDocumentListQuery, usePageListQuery } from '@/query/media'
import { usePageCards } from '@/viewmodels/page-cards'

function uniqueSources<T extends { source_id: string }>(pages: Array<{ items: T[] }> = []) {
  return [
    ...new Map(pages.flatMap((page) => page.items).map((item) => [item.source_id, item])).values(),
  ]
}

export function documentTitle(document: Pick<DocumentResponse, 'name' | 'document_id'>) {
  return document.name?.trim() || `Document ${document.document_id}`
}

export function useDocumentList(library: MaybeRefOrGetter<string | undefined>, pageSize = 12, linkStates: MaybeRefOrGetter<EntityLinkState[]> = []) {
  const query = useDocumentListQuery(
    computed(() => ({
      ...(toValue(library) && { 'filter.library': [toValue(library)!] }),
      ...(toValue(linkStates).length && { 'filter.entity_link_state': toValue(linkStates) }),
      limit: pageSize,
    })),
  )
  return {
    documents: computed(() => uniqueSources<DocumentResponse>(query.data.value?.pages)),
    error: query.error,
    isLoading: query.isPending,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    loadMore: query.fetchNextPage,
    retry: () => (query.isFetchNextPageError.value ? query.fetchNextPage() : query.refetch()),
  }
}

export function useDocumentGroup(document: MaybeRefOrGetter<DocumentResponse>, pageSize = 12, linkStates: MaybeRefOrGetter<EntityLinkState[]> = []) {
  const query = usePageListQuery(
    computed(() => ({
      'filter.library': [toValue(document).library],
      'filter.document_id': [toValue(document).document_id],
      ...(toValue(linkStates).length && { 'filter.entity_link_state': toValue(linkStates) }),
      limit: pageSize,
      return_total_count: true,
    })),
  )
  const registeredCount = usePageListQuery(computed(() => ({
    'filter.library': [toValue(document).library], 'filter.document_id': [toValue(document).document_id], limit: 0, return_total_count: true,
  })), computed(() => toValue(linkStates).length > 0))
  const pages = computed(() => uniqueSources<PageResponse>(query.data.value?.pages))
  return {
    cards: usePageCards(pages),
    totalCount: computed(() => (toValue(linkStates).length ? registeredCount.data.value?.pages[0]?.total_count : query.data.value?.pages[0]?.total_count) ?? null),
    filteredCount: computed(() => query.data.value?.pages[0]?.total_count ?? null),
    error: query.error,
    isLoading: query.isPending,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    loadMore: query.fetchNextPage,
    retry: () => (query.isFetchNextPageError.value ? query.fetchNextPage() : query.refetch()),
  }
}
