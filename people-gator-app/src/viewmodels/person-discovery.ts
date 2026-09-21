import { useQueries, useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { PageResponse } from '@/client'
import type {
  PersonDiscoveryCandidate,
  PersonDiscoveryFace,
} from '@/viewmodels/person-detail.types'
import { fetchEntity } from '@/query/entities'
import { fetchFaceAlignedCrop, fetchFaces, useAssignFacesMutation } from '@/query/faces'
import { queryKeys } from '@/query/keys'
import { fetchPage } from '@/query/media'
import { useObjectUrlMap } from '@/composables/object-url'
import { fetchEntitySearch, fetchFaceSearch } from '@/query/search'

const DISCOVERY_LIMIT = 40
const DISCOVERY_GC_TIME = 60 * 60_000

function percentage(value: number) {
  return Math.round(value <= 1 ? value * 100 : value)
}

export function personDiscoverySignals(faceIds: string[], nameQuery: string) {
  const name = nameQuery.trim()
  return {
    ...(name && { q: [name] }),
    ...(faceIds.length && { q_face_id: faceIds }),
    entity_type: ['person'] as Array<'person'>,
    limit: DISCOVERY_LIMIT,
  }
}

export function usePersonDiscovery(
  personId: MaybeRefOrGetter<string>,
  referenceFaceIds: MaybeRefOrGetter<string[]>,
  nameQuery: MaybeRefOrGetter<string>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  const faceIds = computed(() => [...new Set(toValue(referenceFaceIds))])
  const canSearchFaces = computed(() => toValue(enabled) && faceIds.value.length > 0)

  const faceSearchQuery = useQuery({
    queryKey: computed(() =>
      queryKeys.search.faces({ q_face_id: faceIds.value, limit: DISCOVERY_LIMIT }),
    ),
    queryFn: ({ signal }) =>
      fetchFaceSearch({ q_face_id: faceIds.value, limit: DISCOVERY_LIMIT }, signal),
    enabled: canSearchFaces,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: DISCOVERY_GC_TIME,
  })

  const faceMatches = computed(() =>
    (faceSearchQuery.data.value?.items ?? []).filter(
      (face) => face.entity_id !== toValue(personId),
    ),
  )
  const matchedFaceIds = computed(() => faceMatches.value.map((face) => face.face_id))
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
        queryKey: queryKeys.faces.alignedCrop(faceId, 320),
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
        id: face.face_id,
        portrait: matchedCropUrls.value.get(face.face_id) ?? '',
        portraitLoading:
          !matchedCropUrls.value.has(face.face_id) &&
          (matchedCropQueries.value[index]?.isPending ?? false),
        score: percentage(face.matching_score),
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

  const entitySearchParams = computed(() =>
    personDiscoverySignals(faceIds.value, toValue(nameQuery)),
  )
  const canSearchPeople = computed(
    () => toValue(enabled) && (faceIds.value.length > 0 || Boolean(toValue(nameQuery).trim())),
  )
  const entitySearchQuery = useQuery({
    queryKey: computed(() => queryKeys.search.entities(entitySearchParams.value)),
    queryFn: ({ signal }) => fetchEntitySearch(entitySearchParams.value, signal),
    enabled: canSearchPeople,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: DISCOVERY_GC_TIME,
  })
  const entityMatches = computed(() =>
    (entitySearchQuery.data.value?.items ?? []).filter(
      (entity) =>
        entity.entity_id !== toValue(personId) &&
        (entity.entity_type === 'person' || entity.entity_type === null),
    ),
  )

  const candidateFaceQueries = useQueries({
    queries: computed(() =>
      entityMatches.value.map((entity) => ({
        queryKey: queryKeys.faces.list({ entity_id: entity.entity_id, limit: 1 }),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchFaces({ entity_id: entity.entity_id, limit: 1 }, signal),
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: DISCOVERY_GC_TIME,
      })),
    ),
  })
  const candidatePortraitIds = computed(() =>
    entityMatches.value.map(
      (_entity, index) => candidateFaceQueries.value[index]?.data?.items[0]?.detection_id ?? '',
    ),
  )
  const candidateCropQueries = useQueries({
    queries: computed(() =>
      candidatePortraitIds.value.map((faceId) => ({
        queryKey: queryKeys.faces.alignedCrop(faceId, 160),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchFaceAlignedCrop(faceId, 160, signal),
        enabled: Boolean(faceId),
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: DISCOVERY_GC_TIME,
        retry: false,
      })),
    ),
  })
  const candidateCropBlobs = computed(() => {
    const blobs = new Map<string, Blob>()
    candidatePortraitIds.value.forEach((faceId, index) => {
      const blob = candidateCropQueries.value[index]?.data
      if (faceId && blob instanceof Blob) blobs.set(faceId, blob)
    })
    return blobs
  })
  const candidateCropUrls = useObjectUrlMap(candidateCropBlobs)

  const similarPeople = computed<PersonDiscoveryCandidate[]>(() =>
    entityMatches.value.map((entity, index) => {
      const portraitFaceId = candidatePortraitIds.value[index] ?? ''
      return {
        id: entity.entity_id,
        name: entity.name || 'Unnamed person',
        shortDescription: entity.short_description || '',
        aliases: entity.aliases ?? [],
        portrait: candidateCropUrls.value.get(portraitFaceId) ?? '',
        portraitLoading:
          (candidateFaceQueries.value[index]?.isPending ?? false) ||
          (Boolean(portraitFaceId) &&
            !candidateCropUrls.value.has(portraitFaceId) &&
            (candidateCropQueries.value[index]?.isPending ?? false)),
      }
    }),
  )

  const assignFacesMutation = useAssignFacesMutation()

  return {
    assignFaces: (faceIdsToAssign: string[]) => {
      if (!faceIdsToAssign.length) return
      assignFacesMutation.mutate({
        detectionIds: [...new Set(faceIdsToAssign)],
        entityId: toValue(personId),
      })
    },
    assignmentStatus: assignFacesMutation.status,
    error: computed(
      () =>
        faceSearchQuery.error.value ??
        entitySearchQuery.error.value ??
        assignFacesMutation.error.value,
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
