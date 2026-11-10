import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'

import type { PageResponse, PageSortField } from '@/client'
import { listSortParams, type SortState } from '@/lib/sorting'
import { GALLERY_DEFAULT } from '@/viewmodels/sort-options'
import { useObjectUrlMap } from '@/composables/object-url'
import { fetchPageImage, fetchPages, usePageListQuery } from '@/query/media'
import { queryKeys } from '@/query/keys'

/** Pages requested per API batch; further batches load on demand. */
export const PAGE_GALLERY_BATCH_SIZE = 12
/** Shared with document page cards so thumbnails come from one cache entry. */
export const PAGE_GALLERY_THUMBNAIL_WIDTH = 256

export type PageGalleryItem = {
  sourceId: string
  library: string
  documentId: string
  pageId: string
  label: string
  current: boolean
  matchesSelectedPerson?: boolean | null
  thumbnailUrl: string
  thumbnailLoading: boolean
  thumbnailFailed: boolean
}

/** Stored position when known; archive UUID prefix otherwise. */
export function pageGalleryLabel(pageId: string, number?: number | null) {
  return number == null ? pageId.slice(0, 8) : String(number)
}

/**
 * Registered pages of exactly one library/document in the selected API order:
 * stored page number (default), unknowns last. Sidebar evidence filters do not
 * apply; only the explicit strip person setting narrows the registered pages.
 */
export function useDocumentPageGallery(
  library: MaybeRefOrGetter<string>,
  documentId: MaybeRefOrGetter<string>,
  currentPageId: MaybeRefOrGetter<string>,
  batchSize = PAGE_GALLERY_BATCH_SIZE,
  sort: MaybeRefOrGetter<SortState<PageSortField>> = GALLERY_DEFAULT,
  personId: MaybeRefOrGetter<string> = '',
  selectedPersonId: MaybeRefOrGetter<string | null> = personId,
) {
  const query = usePageListQuery(
    computed(() => ({
      'filter.library': [toValue(library)],
      'filter.document_id': [toValue(documentId)],
      ...(toValue(personId) ? { 'filter.entity_id': [toValue(personId)] } : {}),
      ...listSortParams(toValue(sort)),
      limit: batchSize,
      return_total_count: true,
    })),
    computed(() => Boolean(toValue(library) && toValue(documentId))),
  )
  const pages = computed(() => {
    const unique = new Map<string, PageResponse>()
    for (const batch of query.data.value?.pages ?? []) {
      for (const item of batch.items) {
        // Defensive scoping: never show another library's or document's page.
        if (item.library !== toValue(library) || item.document_id !== toValue(documentId)) continue
        if (!unique.has(item.source_id)) unique.set(item.source_id, item)
      }
    }
    return [...unique.values()]
  })
  const currentLoaded = computed(() =>
    pages.value.some((page) => page.page_id === toValue(currentPageId)),
  )

  // Look up person membership for loaded pages in bounded batches. This also
  // highlights matches while the strip shows every page, without loading faces
  // or mentions separately for each thumbnail.
  const matchChunks = computed(() => {
    if (!toValue(selectedPersonId) || toValue(personId) === toValue(selectedPersonId)) return []
    const ids = pages.value.map((page) => page.source_id)
    return Array.from({ length: Math.ceil(ids.length / 100) }, (_, i) =>
      ids.slice(i * 100, (i + 1) * 100),
    )
  })
  const matchQueries = useQueries({
    queries: computed(() =>
      matchChunks.value.map((ids) => {
        const params = {
          'filter.library': [toValue(library)],
          'filter.document_id': [toValue(documentId)],
          'filter.entity_id': [toValue(selectedPersonId)!],
          'filter.source_id': ids,
          limit: ids.length,
        }
        return {
          queryKey: queryKeys.pages.list(params),
          queryFn: ({ signal }: { signal: AbortSignal }) => fetchPages(params, signal),
        }
      }),
    ),
  })
  const personMatches = computed(
    () =>
      new Map(
        matchChunks.value.flatMap((ids, i) => {
          const result = matchQueries.value[i]?.data
          const found = new Set(result?.items.map((page) => page.source_id))
          return ids.map((id) => [id, result ? found.has(id) : null] as const)
        }),
      ),
  )

  // In the unfiltered strip, locate the current page across batches. A person
  // filter may exclude it, so filtered lists load further batches only on demand.
  watch(
    () => [
      currentLoaded.value,
      query.data.value,
      query.hasNextPage.value,
      query.isFetching.value,
      query.isError.value,
    ],
    () => {
      if (
        !toValue(personId) &&
        !currentLoaded.value &&
        query.data.value &&
        query.hasNextPage.value &&
        !query.isFetching.value &&
        !query.isError.value
      )
        void query.fetchNextPage()
    },
    { immediate: true },
  )

  const thumbnailQueries = useQueries({
    queries: computed(() =>
      pages.value.map((page) => ({
        queryKey: queryKeys.pages.image(page.source_id, PAGE_GALLERY_THUMBNAIL_WIDTH),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchPageImage(page.source_id, PAGE_GALLERY_THUMBNAIL_WIDTH, signal),
        staleTime: Number.POSITIVE_INFINITY,
        // Missing media is an expected fallback state, not a transient failure.
        retry: false,
      })),
    ),
  })
  const thumbnailBlobs = computed(() => {
    const blobs = new Map<string, Blob>()
    pages.value.forEach((page, index) => {
      const data = thumbnailQueries.value[index]?.data
      if (data instanceof Blob) blobs.set(page.source_id, data)
    })
    return blobs
  })
  const thumbnailUrls = useObjectUrlMap(thumbnailBlobs)

  const items = computed<PageGalleryItem[]>(() =>
    pages.value.map((page, index) => ({
      sourceId: page.source_id,
      library: page.library,
      documentId: page.document_id,
      pageId: page.page_id,
      label: pageGalleryLabel(page.page_id, page.page_number),
      current: page.page_id === toValue(currentPageId),
      matchesSelectedPerson: !toValue(selectedPersonId)
        ? false
        : toValue(personId) === toValue(selectedPersonId)
          ? true
          : (personMatches.value.get(page.source_id) ?? null),
      thumbnailUrl: thumbnailUrls.value.get(page.source_id) ?? '',
      thumbnailLoading: thumbnailQueries.value[index]?.isPending ?? false,
      thumbnailFailed: thumbnailQueries.value[index]?.isError ?? false,
    })),
  )

  return {
    items,
    totalCount: computed(() => query.data.value?.pages[0]?.total_count ?? null),
    isLoading: computed(() => query.isPending.value),
    error: computed(() => query.error.value),
    highlightError: computed(() => matchQueries.value.some((result) => result.isError)),
    retryHighlights: () => Promise.all(matchQueries.value.map((result) => result.refetch())),
    hasNextPage: computed(() => query.hasNextPage.value),
    isFetchingNextPage: computed(() => query.isFetchingNextPage.value),
    loadMore: () => {
      if (query.hasNextPage.value && !query.isFetching.value) void query.fetchNextPage()
    },
    retry: () => (query.isFetchNextPageError.value ? query.fetchNextPage() : query.refetch()),
  }
}
