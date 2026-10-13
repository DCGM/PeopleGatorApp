import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntityResponse, PageResponse } from '@/client'
import { fetchEntities } from '@/query/entities'
import { fetchPageImage } from '@/query/media'
import { useObjectUrlMap } from '@/composables/object-url'
import { queryKeys } from '@/query/keys'

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

/** Enrich already loaded pages without refetching their details. */
export function usePageCards(pages: MaybeRefOrGetter<PageResponse[]>) {
  const sourceIds = computed(() => toValue(pages).map((page) => page.source_id))
  const entityQueries = useQueries({
    queries: computed(() =>
      sourceIds.value.map((sourceId) => ({
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
      sourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.image(sourceId, 256),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPageImage(sourceId, 256, signal),
        staleTime: Number.POSITIVE_INFINITY,
      })),
    ),
  })

  const imageBlobs = computed(() => {
    const images = new Map<string, Blob>()
    imageQueries.value.forEach((query, index) => {
      const sourceId = sourceIds.value[index]
      if (sourceId && query.data instanceof Blob) images.set(sourceId, query.data)
    })
    return images
  })
  const imageUrls = useObjectUrlMap(imageBlobs)

  const cards = computed<DocumentSearchCard[]>(() =>
    toValue(pages).map((resolvedPage, index) => {
      const sourceId = resolvedPage.source_id
      const names = sourceEntityNames(entityQueries.value[index]?.data?.items ?? [])
      return {
        sourceId,
        library: resolvedPage.library,
        documentId: resolvedPage.document_id,
        pageId: resolvedPage.page_id,
        names,
        thumbnailUrl: imageUrls.value.get(sourceId) ?? '',
        thumbnailLoading: imageQueries.value[index]?.isPending ?? false,
      }
    }),
  )

  return cards
}
