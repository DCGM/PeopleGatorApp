import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import type { LocationQuery } from 'vue-router'

import type { PageResponse, PageSortField } from '@/client'
import { listSortParams, type SortState } from '@/lib/sorting'
import { GALLERY_DEFAULT } from '@/viewmodels/sort-options'
import { useObjectUrlMap } from '@/composables/object-url'
import { fetchPageImage, usePageListQuery } from '@/query/media'
import { queryKeys } from '@/query/keys'

/** Pages requested per API batch; further batches load on demand. */
export const PAGE_GALLERY_BATCH_SIZE = 12
/** Shared with document page cards so thumbnails come from one cache entry. */
export const PAGE_GALLERY_THUMBNAIL_WIDTH = 256

/** Selections that only make sense on the page where they were made. */
const PAGE_SPECIFIC_QUERY = ['person', 'selectedPerson', 'line', 'page_link_state'] as const

export type PageGalleryItem = {
  sourceId: string
  library: string
  documentId: string
  pageId: string
  label: string
  current: boolean
  thumbnailUrl: string
  thumbnailLoading: boolean
  thumbnailFailed: boolean
}

/** A short, truthful identifier: the archive page UUID prefix, not a page number. */
export function pageGalleryLabel(pageId: string) {
  return pageId.slice(0, 8)
}

/** Keep workspace settings and evidence filters; drop page-specific selections. */
export function pageGalleryQuery(query: LocationQuery): LocationQuery {
  const next = { ...query }
  for (const key of PAGE_SPECIFIC_QUERY) delete next[key]
  return next
}

/**
 * Registered pages of exactly one library/document in the selected API order:
 * archive page ID (default) or last change. Neither is the physical page
 * sequence, which is not recorded. Evidence filters deliberately do not apply:
 * every registered page stays reachable.
 */
export function useDocumentPageGallery(
  library: MaybeRefOrGetter<string>,
  documentId: MaybeRefOrGetter<string>,
  currentPageId: MaybeRefOrGetter<string>,
  batchSize = PAGE_GALLERY_BATCH_SIZE,
  sort: MaybeRefOrGetter<SortState<PageSortField>> = GALLERY_DEFAULT,
) {
  const query = usePageListQuery(
    computed(() => ({
      'filter.library': [toValue(library)],
      'filter.document_id': [toValue(documentId)],
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

  // Load further batches until the current page is present so it can be marked
  // and scrolled into view, including pages outside the first batch.
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
      label: pageGalleryLabel(page.page_id),
      current: page.page_id === toValue(currentPageId),
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
    hasNextPage: computed(() => query.hasNextPage.value),
    isFetchingNextPage: computed(() => query.isFetchingNextPage.value),
    loadMore: () => {
      if (query.hasNextPage.value && !query.isFetching.value) void query.fetchNextPage()
    },
    retry: () => (query.isFetchNextPageError.value ? query.fetchNextPage() : query.refetch()),
  }
}
