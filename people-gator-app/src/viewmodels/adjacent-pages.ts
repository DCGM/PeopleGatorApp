import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import type { PageResponse } from '@/client'
import { usePageListQuery } from '@/query/media'

/** Pages per lookup batch; batches load only until the current page has a neighbour. */
export const ADJACENT_PAGE_BATCH = 100

/**
 * Previous and next registered pages of one document in page-number order
 * (unknown numbers last), independent of strip filters and sorting.
 */
export function useAdjacentPages(
  library: MaybeRefOrGetter<string>,
  documentId: MaybeRefOrGetter<string>,
  pageId: MaybeRefOrGetter<string>,
) {
  const enabled = computed(() => Boolean(toValue(library) && toValue(documentId)))
  const query = usePageListQuery(
    computed(() => ({
      'filter.library': [toValue(library)],
      'filter.document_id': [toValue(documentId)],
      sort: 'page_number' as const,
      sort_direction: 'asc' as const,
      limit: ADJACENT_PAGE_BATCH,
    })),
    enabled,
  )
  const pages = computed<PageResponse[]>(
    () => query.data.value?.pages.flatMap((batch) => batch.items) ?? [],
  )
  const index = computed(() => pages.value.findIndex((page) => page.page_id === toValue(pageId)))
  // Load further batches until the current page and the one after it are known.
  watch(
    () => [index.value, pages.value.length, query.hasNextPage.value, query.isFetching.value],
    () => {
      const needsMore = index.value < 0 || index.value === pages.value.length - 1
      if (needsMore && query.hasNextPage.value && !query.isFetching.value && !query.isError.value)
        void query.fetchNextPage()
    },
    { immediate: true },
  )
  return {
    previous: computed(() => (index.value > 0 ? pages.value[index.value - 1] : undefined)),
    next: computed(() =>
      index.value >= 0 && index.value < pages.value.length - 1
        ? pages.value[index.value + 1]
        : undefined,
    ),
  }
}
