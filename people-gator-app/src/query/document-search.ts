import { useInfiniteQuery, useQueries, type InfiniteData, type QueryKey } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { PageResponse, PageSearchResult, SourceResponse } from '@/client'
import { fetchPage, fetchPageImage, fetchPages, fetchSources } from '@/query/media'
import { useObjectUrlMap } from '@/query/object-url'
import { queryKeys } from '@/query/keys'
import { fetchPageSearch } from '@/query/search'
import { fetchTextMentions } from '@/query/text-mentions'

export type DocumentSearchCard = {
  sourceId: string
  library: string
  documentId: string
  pageId: string
  names: string[]
  thumbnailUrl: string
  thumbnailLoading: boolean
}

type DocumentResultPage = {
  items: Array<PageResponse | PageSearchResult | SourceResponse>
  totalCount: number
  nextPage: string | number | undefined
}

const DOCUMENT_CACHE_TIME = 10 * 60_000
const DOCUMENT_GC_TIME = 60 * 60_000

async function fetchPageSources(afterId: string | undefined, limit: number, signal: AbortSignal) {
  const pageSources: SourceResponse[] = []
  let nextCursor = afterId

  while (pageSources.length < limit) {
    const response = await fetchSources(
      { limit: limit - pageSources.length, after_id: nextCursor },
      signal,
    )
    pageSources.push(...response.items.filter((source) => source.source_type === 'page'))

    const previousCursor = nextCursor
    nextCursor = response.after_id ?? undefined
    if (!nextCursor || nextCursor === previousCursor) break
  }

  return { items: pageSources, nextCursor }
}

export function useDocumentSearch(searchTerm: MaybeRefOrGetter<string>, pageSize = 12) {
  const normalizedSearch = computed(() => toValue(searchTerm).trim())

  const pageResultsQuery = useInfiniteQuery<
    DocumentResultPage,
    Error,
    InfiniteData<DocumentResultPage, string | number>,
    QueryKey,
    string | number
  >({
    queryKey: computed(() =>
      normalizedSearch.value
        ? queryKeys.search.infinitePages({ q: normalizedSearch.value, limit: pageSize })
        : queryKeys.pages.infinite({ limit: pageSize }),
    ),
    queryFn: async ({ pageParam, signal }): Promise<DocumentResultPage> => {
      if (normalizedSearch.value) {
        // Search pages currently has no cursor parameter. Request one look-ahead
        // result and append only the newly revealed slice.
        const pageIndex = typeof pageParam === 'number' ? pageParam : 0
        const pageEnd = (pageIndex + 1) * pageSize
        const response = await fetchPageSearch(
          { q: normalizedSearch.value, limit: pageEnd + 1 },
          signal,
        )
        const hasNextPage = response.items.length > pageEnd

        return {
          items: response.items.slice(pageIndex * pageSize, pageEnd),
          totalCount: hasNextPage ? pageEnd + 1 : response.items.length,
          nextPage: hasNextPage ? pageIndex + 1 : undefined,
        }
      }

      // Weaviate rejects cursors combined with the implicit page-type filter
      // used by `/pages`. Enumerate the unfiltered source collection by cursor,
      // retain page sources, then resolve their page metadata below.
      const afterId = typeof pageParam === 'string' ? pageParam : undefined
      const [response, pageCount] = await Promise.all([
        fetchPageSources(afterId, pageSize, signal),
        afterId ? Promise.resolve(undefined) : fetchPages({ limit: 0 }, signal),
      ])
      return {
        items: response.items,
        totalCount: pageCount?.total_count ?? 0,
        nextPage: response.nextCursor,
      }
    },
    initialPageParam: 0 as string | number,
    getNextPageParam: (lastPage) => lastPage.nextPage,
    staleTime: DOCUMENT_CACHE_TIME,
    gcTime: DOCUMENT_GC_TIME,
    refetchOnWindowFocus: false,
  })

  const resultSourceIds = computed(() => {
    const sourceIds = new Set<string>()
    for (const page of pageResultsQuery.data.value?.pages ?? []) {
      for (const item of page.items) {
        sourceIds.add('page_source_id' in item ? item.page_source_id : item.source_id)
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

  const mentionQueries = useQueries({
    queries: computed(() =>
      resultSourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.textMentions.list({ source_id: sourceId, limit: 100 }),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchTextMentions({ source_id: sourceId, limit: 100 }, signal),
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
      const names = [
        ...new Set((mentionQueries.value[index]?.data?.items ?? []).map((item) => item.name)),
      ]
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
      if (normalizedSearch.value) return resultSourceIds.value.length
      return pageResultsQuery.data.value?.pages[0]?.totalCount ?? 0
    }),
  }
}
