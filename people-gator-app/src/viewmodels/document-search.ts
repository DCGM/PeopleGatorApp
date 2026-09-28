import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntityResponse, PageResponse } from '@/client'
import { pageContentFilter, type PageContentFilter } from '@/viewmodels/assignment'
import { fetchEntities } from '@/query/entities'
import { fetchPage, fetchPageImage } from '@/query/media'
import { useObjectUrlMap } from '@/composables/object-url'
import { queryKeys } from '@/query/keys'
import { usePageResultsQuery } from '@/query/search'

export type DocumentSearchCard = {
  sourceId: string
  library: string
  documentId: string
  pageId: string
  names: string[]
  thumbnailUrl: string
  thumbnailLoading: boolean
}

const DOCUMENT_CACHE_TIME = 10 * 60_000
const DOCUMENT_GC_TIME = 60 * 60_000

export function sourceEntityNames(
  entities: Array<Pick<EntityResponse, 'name'> | { name?: string | null }>,
) {
  const seen = new Set<string>()
  const names: string[] = []

  for (const entity of entities) {
    const normalizedName = entity.name?.trim()
    if (!normalizedName || seen.has(normalizedName)) continue
    seen.add(normalizedName)
    names.push(normalizedName)
    if (names.length >= 3) break
  }

  return names
}

export function useDocumentSearch(
  searchTerm: MaybeRefOrGetter<string>,
  filter: MaybeRefOrGetter<PageContentFilter>,
  pageSize = 12,
) {
  const normalizedSearch = computed(() => toValue(searchTerm).trim())
  const contentFilter = computed(() => pageContentFilter(toValue(filter)))
  const pageResultsQuery = usePageResultsQuery(
    computed(() => ({
      query: normalizedSearch.value,
      ...contentFilter.value,
      limit: pageSize,
    })),
  )

  const resultSourceIds = computed(() => {
    const sourceIds = new Set<string>()
    for (const page of pageResultsQuery.data.value?.pages ?? []) {
      for (const item of page.items) {
        sourceIds.add(item.source_id)
      }
    }
    return [...sourceIds]
  })

  const pageQueries = useQueries({
    queries: computed(() =>
      resultSourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.detail(sourceId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPage(sourceId, signal),
        retry: false,
        staleTime: DOCUMENT_CACHE_TIME,
        gcTime: DOCUMENT_GC_TIME,
      })),
    ),
  })

  const resolvedPages = computed(() => {
    const pages = new Map<string, PageResponse>()
    pageQueries.value.forEach((query, index) => {
      const pageResult = query.data
      const sourceId = resultSourceIds.value[index]
      if (sourceId && pageResult) pages.set(sourceId, pageResult)
    })
    return pages
  })

  const entityQueries = useQueries({
    queries: computed(() =>
      resultSourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.entities.list({ 'filter.source_id': [sourceId], limit: 3 }),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchEntities({ 'filter.source_id': [sourceId], limit: 3 }, signal),
        staleTime: DOCUMENT_CACHE_TIME,
        gcTime: DOCUMENT_GC_TIME,
      })),
    ),
  })

  const imageQueries = useQueries({
    queries: computed(() =>
      resultSourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.image(sourceId, 256),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPageImage(sourceId, 256, signal),
        staleTime: Number.POSITIVE_INFINITY,
      })),
    ),
  })

  const imageBlobs = computed(() => {
    const images = new Map<string, Blob>()
    imageQueries.value.forEach((query, index) => {
      const sourceId = resultSourceIds.value[index]
      if (sourceId && query.data instanceof Blob) images.set(sourceId, query.data)
    })
    return images
  })
  const imageUrls = useObjectUrlMap(imageBlobs)

  const cards = computed<DocumentSearchCard[]>(() =>
    resultSourceIds.value.flatMap((sourceId, index) => {
      const resolvedPage = resolvedPages.value.get(sourceId)
      if (!resolvedPage) return []
      const names = sourceEntityNames(entityQueries.value[index]?.data?.items ?? [])
      return [
        {
          sourceId,
          library: resolvedPage.library,
          documentId: resolvedPage.document_id,
          pageId: resolvedPage.page_id,
          names,
          thumbnailUrl: imageUrls.value.get(sourceId) ?? '',
          thumbnailLoading: imageQueries.value[index]?.isPending ?? false,
        },
      ]
    }),
  )

  const isLoading = computed(
    () => pageResultsQuery.isPending.value || pageQueries.value.some((query) => query.isPending),
  )

  return {
    cards,
    error: pageResultsQuery.error,
    hasNextPage: pageResultsQuery.hasNextPage,
    isFetchingNextPage: pageResultsQuery.isFetchingNextPage,
    isLoading,
    loadMore: pageResultsQuery.fetchNextPage,
    resultCount: computed(() => {
      return pageResultsQuery.data.value?.pages[0]?.totalCount ?? 0
    }),
  }
}
