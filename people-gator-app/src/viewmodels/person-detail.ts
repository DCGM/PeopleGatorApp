import type { SharedQuery } from './shared-filters'
import { useQueries } from '@tanstack/vue-query'
import { computed, type MaybeRefOrGetter, toValue } from 'vue'

import { linkMetadata } from '@/lib/entity-links'
import type { EntityLinkState, FaceSortField, PageResponse, TextMentionSortField } from '@/client'
import type {
  PersonIdentifiers,
  PersonFace,
  PersonMention,
  PersonProfile,
  PersonProcessingInfo,
} from '@/viewmodels/person-detail.types'
import { useEntityQuery, usePatchEntityMutation } from '@/query/entities'
import { fetchFaceAlignedCrop, useFaceListQuery } from '@/query/faces'
import { fetchPage, fetchPageImage } from '@/query/media'
import { useObjectUrlMap } from '@/composables/object-url'
import { queryKeys } from '@/query/keys'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { useTextMentionListQuery } from '@/query/text-mentions'
import { listSortParams, sortParams, type SortState } from '@/lib/sorting'
import { FACE_DEFAULT, MENTION_DEFAULT } from '@/viewmodels/sort-options'
import { useMentionViews } from '@/viewmodels/person-mentions'

function percentage(value: number) {
  return Math.round(value <= 1 ? value * 100 : value)
}

const PERSON_DETAIL_GC_TIME = 60 * 60_000

export function usePersonDetail(
  personId: MaybeRefOrGetter<string>,
  linkStates: MaybeRefOrGetter<EntityLinkState[]> = [],
  evidence: MaybeRefOrGetter<SharedQuery> = {},
  evidenceValid: MaybeRefOrGetter<boolean> = true,
  matchedFaceIds: MaybeRefOrGetter<string[]> = [],
  faceSort: MaybeRefOrGetter<SortState<FaceSortField>> = FACE_DEFAULT,
  mentionSort: MaybeRefOrGetter<SortState<TextMentionSortField>> = MENTION_DEFAULT,
  mentionsEnabled: MaybeRefOrGetter<boolean> = true,
) {
  const entityQuery = useEntityQuery(personId)
  const patchEntity = usePatchEntityMutation()
  const touchedUserId = computed(() => entityQuery.data.value?.last_touched_by_user_id ?? '')
  const touchedApiKeyId = computed(() => entityQuery.data.value?.last_touched_by_api_key_id ?? '')
  const processingUsers = usePeopleFilterOptions('user', touchedUserId, () =>
    Boolean(touchedUserId.value),
  )
  const processingApiKeys = usePeopleFilterOptions('api-key', touchedApiKeyId, () =>
    Boolean(touchedApiKeyId.value),
  )
  const processing = computed<PersonProcessingInfo>(() => ({
    touchedAt: entityQuery.data.value?.last_touched_at ?? null,
    userId: touchedUserId.value || null,
    userLabel: processingUsers.labels.value[touchedUserId.value] || touchedUserId.value || null,
    apiKeyId: touchedApiKeyId.value || null,
    apiKeyLabel:
      processingApiKeys.labels.value[touchedApiKeyId.value] || touchedApiKeyId.value || null,
  }))

  const hasPerson = computed(() => Boolean(toValue(personId)))
  // The same evidence scope serves the flat list, the exact-appearance groups
  // and each group's occurrences, so counts and members always agree.
  const mentionFilters = computed(() => ({
    ...toValue(evidence),
    'filter.entity_id': [toValue(personId)],
    'filter.entity_link_state': toValue(linkStates).length ? toValue(linkStates) : undefined,
  }))
  const faceQuery = useFaceListQuery(
    computed(() => ({
      ...toValue(evidence),
      'filter.entity_id': [toValue(personId)],
      'filter.entity_link_state': toValue(linkStates).length ? toValue(linkStates) : undefined,
      ...listSortParams(toValue(faceSort)),
      limit: 100,
      return_total_count: true,
    })),
    computed(() => hasPerson.value && toValue(evidenceValid)),
  )
  const mentionQuery = useTextMentionListQuery(
    computed(() => ({
      ...mentionFilters.value,
      ...sortParams(toValue(mentionSort)),
      limit: 100,
      return_total_count: true,
    })),
    computed(() => hasPerson.value && toValue(evidenceValid) && toValue(mentionsEnabled)),
  )
  const mentionTotal = useTextMentionListQuery(
    computed(() => ({ ...mentionFilters.value, limit: 0, return_total_count: true })),
    computed(() => hasPerson.value && toValue(evidenceValid) && !toValue(mentionsEnabled)),
  )

  const matchedFaces = useFaceListQuery(
    computed(() => ({
      ...toValue(evidence),
      'filter.entity_id': [toValue(personId)],
      'filter.detection_id': toValue(matchedFaceIds),
      limit: 100,
    })),
    computed(() => hasPerson.value && toValue(evidenceValid) && toValue(matchedFaceIds).length > 0),
  )
  // Witnesses from the originating search are pinned first and labelled; the
  // remaining faces follow the selected order.
  const matchedIds = computed(
    () =>
      new Set(
        (matchedFaces.data.value?.pages ?? [])
          .flatMap((page) => page.items)
          .map((face) => face.detection_id),
      ),
  )
  const faceRecords = computed(() => [
    ...new Map(
      [
        ...(matchedFaces.data.value?.pages ?? []).flatMap((page) => page.items),
        ...(faceQuery.data.value?.pages ?? []).flatMap((page) => page.items),
      ].map((face) => [face.detection_id, face]),
    ).values(),
  ])
  const discoveryFaces = useFaceListQuery(
    computed(() => ({ 'filter.entity_id': [toValue(personId)], limit: 100 })),
    hasPerson,
  )
  const discoveryFaceRecords = computed(() =>
    (discoveryFaces.data.value?.pages ?? []).flatMap((page) => page.items),
  )
  const faceEmbeddingModel = computed(
    () =>
      discoveryFaceRecords.value.find((face) => face.embeddings?.length)?.embeddings?.[0] ?? null,
  )
  const similarityFaceIds = computed(() => {
    const model = faceEmbeddingModel.value
    if (!model) return []
    return discoveryFaceRecords.value
      .filter((face) => face.embeddings?.includes(model))
      .map((face) => face.detection_id)
  })
  const mentionRecords = computed(() =>
    (mentionQuery.data.value?.pages ?? []).flatMap((page) => page.items),
  )
  const sourceIds = computed(() => [...new Set(faceRecords.value.map((face) => face.source_id))])

  const pageQueries = useQueries({
    queries: computed(() =>
      sourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.detail(sourceId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPage(sourceId, signal),
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: PERSON_DETAIL_GC_TIME,
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
        gcTime: PERSON_DETAIL_GC_TIME,
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

  // Aligned face crops (ArcFace-aligned, 1:1) keyed by detection id.
  const detectionIds = computed(() => faceRecords.value.map((face) => face.detection_id))
  const alignedCropQueries = useQueries({
    queries: computed(() =>
      detectionIds.value.map((detectionId) => ({
        queryKey: queryKeys.faceCrops.aligned(detectionId, 256),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchFaceAlignedCrop(detectionId, 256, signal),
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: PERSON_DETAIL_GC_TIME,
        retry: false,
      })),
    ),
  })
  const alignedCropBlobs = computed(() => {
    const result = new Map<string, Blob>()
    detectionIds.value.forEach((detectionId, index) => {
      const blob = alignedCropQueries.value[index]?.data
      if (blob instanceof Blob) result.set(detectionId, blob)
    })
    return result
  })
  const alignedCropUrls = useObjectUrlMap(alignedCropBlobs)

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
    faceRecords.value.flatMap((face, faceIndex) => {
      const page = pages.value.get(face.source_id)
      const portrait =
        alignedCropUrls.value.get(face.detection_id) ?? imageUrls.value.get(face.source_id) ?? ''
      const pageImageIndex = imageSourceIds.value.indexOf(face.source_id)
      return [
        {
          ...linkMetadata(face),
          matched: matchedIds.value.has(face.detection_id),
          metadata: face,
          sourceId: face.source_id,
          sourceLoading:
            pageQueries.value[sourceIds.value.indexOf(face.source_id)]?.isPending ?? false,
          id: face.detection_id,
          portrait,
          portraitLoading:
            !portrait &&
            ((alignedCropQueries.value[faceIndex]?.isPending ?? false) ||
              (pageImageIndex >= 0 && (imageQueries.value[pageImageIndex]?.isPending ?? false))),
          confidence: percentage(face.confidence),
          library: page?.library ?? 'Source unavailable',
          documentId: page?.document_id ?? face.source_id,
          pageId: page?.page_id ?? '',
          pageLabel: page?.page_id ?? '',
          position: face.bounding_box,
        },
      ]
    }),
  )

  const mentions = useMentionViews(mentionRecords)

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

  function updateIdentifiers(nextIdentifiers: PersonIdentifiers) {
    patchEntity.mutate({
      entityId: toValue(personId),
      body: {
        wikidata_id: nextIdentifiers.wikidataId || null,
        nlcr_authority_id: nextIdentifiers.nationalLibraryAuthorityId || null,
      },
    })
  }

  return {
    missingMatchedFaces: computed(
      () =>
        !matchedFaces.isPending.value &&
        toValue(matchedFaceIds).some(
          (id) => !faceRecords.value.some((face) => face.detection_id === id),
        ),
    ),
    entity: entityQuery.data,
    faceError: faceQuery.error,
    mentionError: mentionQuery.error,
    faceLoading: faceQuery.isPending,
    mentionLoading: mentionQuery.isPending,
    retryFaces: () => faceQuery.refetch(),
    retryMentions: () => mentionQuery.refetch(),
    hasMoreFaces: faceQuery.hasNextPage,
    hasMoreMentions: mentionQuery.hasNextPage,
    loadingMoreFaces: faceQuery.isFetchingNextPage,
    loadingMoreMentions: mentionQuery.isFetchingNextPage,
    loadMoreFaces: () => faceQuery.fetchNextPage(),
    loadMoreMentions: () => mentionQuery.fetchNextPage(),
    error: entityQuery.error,
    faceEmbeddingModel,
    faceCount: computed(() => faceQuery.data.value?.pages[0]?.total_count ?? 0),
    faceIds: similarityFaceIds,
    faces,
    identifiers,
    isLoading: computed(
      () =>
        entityQuery.isPending.value || faceQuery.isPending.value || mentionQuery.isPending.value,
    ),
    libraryCount: computed(() => new Set(faces.value.map((face) => face.library)).size),
    mentionCount: computed(
      () =>
        (toValue(mentionsEnabled) ? mentionQuery : mentionTotal).data.value?.pages[0]
          ?.total_count ?? 0,
    ),
    mentionFilters,
    mentions,
    // Weaviate stores no portrait; PostgreSQL leaves none only without linked
    // faces. Fall back to the first loaded face once the entity is known.
    portraitFaceId: computed(() => {
      const entity = entityQuery.data.value
      return entity ? (entity.thumbnail_face_id ?? faceRecords.value[0]?.detection_id) : undefined
    }),
    profile,
    processing,
    updateProfile,
    updateIdentifiers,
    updateStatus: patchEntity.status,
  }
}
