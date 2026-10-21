import type { EvidenceQuery } from './evidence-filters'
import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntitySortField, FaceSortField, PageResponse } from '@/client'
import { sortParams, type SortState } from '@/lib/sorting'
import { RELEVANCE } from '@/viewmodels/sort-options'
import type {
  PersonDiscoveryCandidate,
  PersonDiscoveryFace,
} from '@/viewmodels/person-detail.types'
import { fetchEntity, useMergeEntitiesMutation } from '@/query/entities'
import { fetchFaceAlignedCrop, useAssignFacesMutation } from '@/query/faces'
import { queryKeys } from '@/query/keys'
import { fetchPage } from '@/query/media'
import { useObjectUrlMap } from '@/composables/object-url'
import { useEntitySearchQuery, useFaceSearchQuery } from '@/query/search'

const DISCOVERY_LIMIT = 40
const DISCOVERY_GC_TIME = 60 * 60_000

function percentage(value: number) {
  return Math.round(value <= 1 ? value * 100 : value)
}

export function personDiscoverySignals(
  faceIds: string[],
  faceEmbeddingModel: string | null,
  nameQuery: string,
) {
  const name = nameQuery.trim()
  return {
    ...(name && { 'query.text': [name] }),
    ...(faceIds.length &&
      faceEmbeddingModel && {
        'query.face_id': faceIds,
        'query.face_embedding_model': faceEmbeddingModel,
      }),
    'filter.entity_type': ['person'] as Array<'person'>,
    limit: DISCOVERY_LIMIT,
  }
}

export function usePersonDiscovery(
  personId: MaybeRefOrGetter<string>,
  referenceFaceIds: MaybeRefOrGetter<string[]>,
  referenceFaceModel: MaybeRefOrGetter<string | null>,
  nameQuery: MaybeRefOrGetter<string>,
  enabled: MaybeRefOrGetter<boolean>,
  evidence: MaybeRefOrGetter<EvidenceQuery> = {},
  faceSort: MaybeRefOrGetter<SortState<FaceSortField>> = RELEVANCE,
  peopleSort: MaybeRefOrGetter<SortState<EntitySortField>> = RELEVANCE,
) {
  const faceIds = computed(() => [...new Set(toValue(referenceFaceIds))])
  const hasFaceSignal = computed(
    () => faceIds.value.length > 0 && Boolean(toValue(referenceFaceModel)),
  )
  const canSearchFaces = computed(() => toValue(enabled) && hasFaceSignal.value)

  const faceSearchQuery = useFaceSearchQuery(
    computed(() => ({
      ...toValue(evidence),
      'query.face_id': faceIds.value,
      'query.face_embedding_model': toValue(referenceFaceModel) ?? undefined,
      ...sortParams(toValue(faceSort)),
      limit: DISCOVERY_LIMIT,
    })),
    canSearchFaces,
  )

  const faceMatches = computed(() =>
    (faceSearchQuery.data.value?.pages ?? [])
      .flatMap((page) => page.items)
      .filter((face) => face.entity_id !== toValue(personId)),
  )
  const matchedFaceIds = computed(() => faceMatches.value.map((face) => face.detection_id))
  const matchedSourceIds = computed(() => [
    ...new Set(faceMatches.value.flatMap((face) => (face.source_id ? [face.source_id] : []))),
  ])
  const assignedEntityIds = computed(() => [
    ...new Set(faceMatches.value.flatMap((face) => (face.entity_id ? [face.entity_id] : []))),
  ])

  const assignedEntityQueries = useQueries({
    queries: computed(() =>
      assignedEntityIds.value.map((entityId) => ({
        queryKey: queryKeys.entities.detail(entityId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchEntity(entityId, signal),
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: DISCOVERY_GC_TIME,
      })),
    ),
  })
  const assignedEntityNames = computed(() => {
    const names = new Map<string, string>()
    assignedEntityIds.value.forEach((entityId, index) => {
      const entity = assignedEntityQueries.value[index]?.data
      names.set(entityId, entity?.name || entityId)
    })
    return names
  })

  const matchedCropQueries = useQueries({
    queries: computed(() =>
      matchedFaceIds.value.map((faceId) => ({
        queryKey: queryKeys.faceCrops.aligned(faceId, 320),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchFaceAlignedCrop(faceId, 320, signal),
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: DISCOVERY_GC_TIME,
        retry: false,
      })),
    ),
  })
  const matchedCropBlobs = computed(() => {
    const blobs = new Map<string, Blob>()
    matchedFaceIds.value.forEach((faceId, index) => {
      const blob = matchedCropQueries.value[index]?.data
      if (blob instanceof Blob) blobs.set(faceId, blob)
    })
    return blobs
  })
  const matchedCropUrls = useObjectUrlMap(matchedCropBlobs)

  const matchedPageQueries = useQueries({
    queries: computed(() =>
      matchedSourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.detail(sourceId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPage(sourceId, signal),
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: DISCOVERY_GC_TIME,
      })),
    ),
  })
  const matchedPages = computed(() => {
    const pages = new Map<string, PageResponse>()
    matchedSourceIds.value.forEach((sourceId, index) => {
      const page = matchedPageQueries.value[index]?.data
      if (page) pages.set(sourceId, page)
    })
    return pages
  })

  const similarFaces = computed<PersonDiscoveryFace[]>(() =>
    faceMatches.value.map((face, index) => {
      const page = face.source_id ? matchedPages.value.get(face.source_id) : undefined
      return {
        id: face.detection_id,
        portrait: matchedCropUrls.value.get(face.detection_id) ?? '',
        portraitLoading:
          !matchedCropUrls.value.has(face.detection_id) &&
          (matchedCropQueries.value[index]?.isPending ?? false),
        score: percentage(face.face_score ?? face.score),
        assignedEntityId: face.entity_id ?? null,
        assignedEntityName: face.entity_id
          ? (assignedEntityNames.value.get(face.entity_id) ?? face.entity_id)
          : undefined,
        library: page?.library,
        documentId: page?.document_id,
        pageId: page?.page_id,
        pageLabel: page?.page_id,
      }
    }),
  )

  const entitySearchParams = computed(() => ({
    ...personDiscoverySignals(faceIds.value, toValue(referenceFaceModel), toValue(nameQuery)),
    ...toValue(evidence),
    ...sortParams(toValue(peopleSort)),
  }))
  const canSearchPeople = computed(
    () => toValue(enabled) && (hasFaceSignal.value || Boolean(toValue(nameQuery).trim())),
  )
  const entitySearchQuery = useEntitySearchQuery(entitySearchParams, canSearchPeople)
  const entityMatches = computed(() =>
    (entitySearchQuery.data.value?.pages ?? [])
      .flatMap((page) => page.items)
      .filter(
        (entity) => entity.entity_id !== toValue(personId) && entity.entity_type === 'person',
      ),
  )

  const similarPeople = computed<PersonDiscoveryCandidate[]>(() =>
    entityMatches.value.map((entity) => {
      return {
        id: entity.entity_id,
        matchedFaceIds: entity.matched_detection_ids ?? [],
        name: entity.name || 'Unnamed person',
        shortDescription: entity.short_description || '',
        aliases: entity.aliases ?? [],
        // Stores without persisted portraits (Weaviate) show the matched face.
        thumbnailFaceId: entity.thumbnail_face_id ?? entity.matched_detection_ids?.[0],
      }
    }),
  )

  const assignFacesMutation = useAssignFacesMutation()
  const mergeEntitiesMutation = useMergeEntitiesMutation()

  return {
    assignFaces: (faceIdsToAssign: string[]) => {
      if (!faceIdsToAssign.length) return
      assignFacesMutation.mutate({
        detectionIds: [...new Set(faceIdsToAssign)],
        entityId: toValue(personId),
      })
    },
    assignmentStatus: assignFacesMutation.status,
    mergePeople: (sourceEntityIds: string[]) => {
      const uniqueSourceIds = [...new Set(sourceEntityIds)].filter((id) => id !== toValue(personId))
      if (!uniqueSourceIds.length) return
      mergeEntitiesMutation.mutate({
        targetEntityId: toValue(personId),
        sourceEntityIds: uniqueSourceIds,
      })
    },
    mergeStatus: mergeEntitiesMutation.status,
    error: computed(
      () =>
        faceSearchQuery.error.value ??
        entitySearchQuery.error.value ??
        assignFacesMutation.error.value ??
        mergeEntitiesMutation.error.value,
    ),
    isLoadingFaces: computed(
      () =>
        canSearchFaces.value &&
        (faceSearchQuery.isPending.value || faceSearchQuery.isFetching.value),
    ),
    isLoadingPeople: computed(
      () =>
        canSearchPeople.value &&
        (entitySearchQuery.isPending.value || entitySearchQuery.isFetching.value),
    ),
    similarFaces,
    similarPeople,
  }
}
