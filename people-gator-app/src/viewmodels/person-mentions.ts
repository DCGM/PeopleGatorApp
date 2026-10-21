import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  lookupDocumentRouteApiV1DocumentsLookupGet,
  type DocumentResponse,
  type PageResponse,
  type TextMentionResponse,
} from '@/client'
import { linkMetadata } from '@/lib/entity-links'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'
import { fetchPage } from '@/query/media'
import { documentTitle } from '@/viewmodels/document-list'
import type { PersonMention } from '@/viewmodels/person-detail.types'

const MENTION_SOURCE_GC_TIME = 60 * 60_000

/**
 * Present mention records with their source page and a recognizable document
 * name. A missing document falls back to its archive ID; a missing page keeps
 * the mention visible with an unavailable source.
 */
export function useMentionViews(records: MaybeRefOrGetter<TextMentionResponse[]>) {
  const sourceIds = computed(() => [
    ...new Set(toValue(records).map((mention) => mention.source_id)),
  ])
  const pageQueries = useQueries({
    queries: computed(() =>
      sourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.detail(sourceId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPage(sourceId, signal),
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: MENTION_SOURCE_GC_TIME,
      })),
    ),
  })
  const pages = computed(() => {
    const result = new Map<string, PageResponse>()
    sourceIds.value.forEach((sourceId, index) => {
      const page = pageQueries.value[index]?.data
      if (page) result.set(sourceId, page)
    })
    return result
  })
  const documentKeys = computed(() => [
    ...new Map(
      [...pages.value.values()].map((page) => [
        `${page.library}\u0000${page.document_id}`,
        { library: page.library, documentId: page.document_id },
      ]),
    ).values(),
  ])
  const documentQueries = useQueries({
    queries: computed(() =>
      documentKeys.value.map(({ library, documentId }) => ({
        queryKey: queryKeys.documents.lookup(library, documentId),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          responseData(
            lookupDocumentRouteApiV1DocumentsLookupGet({
              query: { library, document_id: documentId },
              signal,
              throwOnError: true,
            }),
          ),
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: MENTION_SOURCE_GC_TIME,
      })),
    ),
  })
  const documents = computed(() => {
    const result = new Map<string, DocumentResponse>()
    documentKeys.value.forEach(({ library, documentId }, index) => {
      const document = documentQueries.value[index]?.data
      if (document) result.set(`${library}\u0000${documentId}`, document)
    })
    return result
  })

  return computed<PersonMention[]>(() =>
    toValue(records).map((mention) => {
      const page = pages.value.get(mention.source_id)
      const document = page && documents.value.get(`${page.library}\u0000${page.document_id}`)
      return {
        ...linkMetadata(mention),
        metadata: mention,
        sourceId: mention.source_id,
        sourceLoading:
          pageQueries.value[sourceIds.value.indexOf(mention.source_id)]?.isPending ?? false,
        id: mention.mention_id,
        excerpt: mention.context || mention.name,
        matchedText: mention.name,
        library: page?.library ?? 'Source unavailable',
        documentId: page?.document_id ?? mention.source_id,
        documentTitle: document
          ? documentTitle(document)
          : (page?.document_id ?? mention.source_id),
        pageId: page?.page_id ?? '',
        pageLabel: page?.page_id ?? '',
      }
    }),
  )
}
