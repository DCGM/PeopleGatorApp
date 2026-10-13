import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { DocumentResponse, PageResponse } from '@/client'
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

export function useDocumentList(library: MaybeRefOrGetter<string | undefined>, pageSize = 12) {
  const query = useDocumentListQuery(
    computed(() => ({
      ...(toValue(library) && { 'filter.library': [toValue(library)!] }),
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
    retry: query.refetch,
  }
}

export function useDocumentGroup(document: MaybeRefOrGetter<DocumentResponse>, pageSize = 12) {
  const query = usePageListQuery(
    computed(() => ({
      'filter.library': [toValue(document).library],
      'filter.document_id': [toValue(document).document_id],
      limit: pageSize,
      return_total_count: true,
    })),
  )
  const pages = computed(() => uniqueSources<PageResponse>(query.data.value?.pages))
  return {
    cards: usePageCards(pages),
    totalCount: computed(() => query.data.value?.pages[0]?.total_count ?? null),
    error: query.error,
    isLoading: query.isPending,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    loadMore: query.fetchNextPage,
    retry: query.refetch,
  }
}
