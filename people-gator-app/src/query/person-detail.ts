import { useQueries, useQuery } from '@tanstack/vue-query'
import { computed, type MaybeRefOrGetter, toValue } from 'vue'

import type { PageResponse } from '@/client'
import type {
  PersonFace,
  PersonMention,
  PersonProfile,
} from '@/components/custom/person-detail.types'
import { useEntityQuery, usePatchEntityMutation } from '@/query/entities'
import { fetchFaces } from '@/query/faces'
import { fetchPage, fetchPageImage } from '@/query/media'
import { useObjectUrlMap } from '@/query/object-url'
import { queryKeys } from '@/query/keys'
import { fetchTextMentions } from '@/query/text-mentions'

function percentage(value: number) {
  return Math.round(value <= 1 ? value * 100 : value)
}

export function usePersonDetail(personId: MaybeRefOrGetter<string>) {
  const entityQuery = useEntityQuery(personId)
  const patchEntity = usePatchEntityMutation()

  const faceQuery = useQuery({
    queryKey: computed(() => queryKeys.faces.list({ entity_id: toValue(personId), limit: 100 })),
    queryFn: ({ signal }) => fetchFaces({ entity_id: toValue(personId), limit: 100 }, signal),
    enabled: computed(() => Boolean(toValue(personId))),
  })
  const mentionQuery = useQuery({
    queryKey: computed(() =>
      queryKeys.textMentions.list({ entity_id: toValue(personId), limit: 100 }),
    ),
    queryFn: ({ signal }) =>
      fetchTextMentions({ entity_id: toValue(personId), limit: 100 }, signal),
    enabled: computed(() => Boolean(toValue(personId))),
  })

  const faceRecords = computed(() => faceQuery.data.value?.items ?? [])
  const mentionRecords = computed(() => mentionQuery.data.value?.items ?? [])
  const sourceIds = computed(() => [
    ...new Set([
      ...faceRecords.value.map((face) => face.source_id),
      ...mentionRecords.value.map((mention) => mention.source_id),
    ]),
  ])

  const pageQueries = useQueries({
    queries: computed(() =>
      sourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.detail(sourceId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPage(sourceId, signal),
        retry: false,
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

  const imageQueries = useQueries({
    queries: computed(() =>
      [...pages.value.keys()].map((sourceId) => ({
        queryKey: queryKeys.pages.image(sourceId, 256),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPageImage(sourceId, 256, signal),
        staleTime: Number.POSITIVE_INFINITY,
      })),
    ),
  })
  const imageSourceIds = computed(() => [...pages.value.keys()])
  const imageBlobs = computed(() => {
    const result = new Map<string, Blob>()
    imageSourceIds.value.forEach((sourceId, index) => {
      const blob = imageQueries.value[index]?.data
      if (blob instanceof Blob) result.set(sourceId, blob)
    })
    return result
  })
  const imageUrls = useObjectUrlMap(imageBlobs)

  const profile = computed<PersonProfile>(() => ({
    name: entityQuery.data.value?.name || 'Unnamed person',
    shortDescription: entityQuery.data.value?.short_description || '',
    article: entityQuery.data.value?.description || '',
    aliases: entityQuery.data.value?.aliases ?? [],
  }))
  const identifiers = computed(() => ({
    wikidataId: entityQuery.data.value?.wikidata_id ?? '',
    nationalLibraryAuthorityId: entityQuery.data.value?.nlcr_authority_id ?? '',
  }))

  const faces = computed<PersonFace[]>(() =>
    faceRecords.value.flatMap((face) => {
      const page = pages.value.get(face.source_id)
      if (!page) return []
      return [
        {
          id: face.detection_id,
          portrait: imageUrls.value.get(face.source_id) ?? '',
          confidence: percentage(face.confidence),
          library: page.library,
          documentId: page.document_id,
          pageId: page.page_id,
          pageLabel: page.page_id,
          position: face.bounding_box,
        },
      ]
    }),
  )

  const mentions = computed<PersonMention[]>(() =>
    mentionRecords.value.flatMap((mention) => {
      const page = pages.value.get(mention.source_id)
      if (!page) return []
      return [
        {
          id: mention.mention_id,
          excerpt: mention.context || mention.name,
          matchedText: mention.name,
          library: page.library,
          documentId: page.document_id,
          documentTitle: page.document_id,
          pageId: page.page_id,
          pageLabel: page.page_id,
        },
      ]
    }),
  )

  function updateProfile(nextProfile: PersonProfile) {
    patchEntity.mutate({
      entityId: toValue(personId),
      body: {
        name: nextProfile.name,
        short_description: nextProfile.shortDescription || null,
        description: nextProfile.article || null,
        aliases: nextProfile.aliases,
      },
    })
  }

  return {
    entity: entityQuery.data,
    error: entityQuery.error,
    faces,
    identifiers,
    isLoading: computed(
      () =>
        entityQuery.isPending.value || faceQuery.isPending.value || mentionQuery.isPending.value,
    ),
    libraryCount: computed(() => new Set(faces.value.map((face) => face.library)).size),
    mentions,
    portrait: computed(() => faces.value[0]?.portrait ?? ''),
    profile,
    updateProfile,
    updateStatus: patchEntity.status,
  }
}
